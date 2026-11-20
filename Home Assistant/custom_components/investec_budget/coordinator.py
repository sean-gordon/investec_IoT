"""Fetches Investec data, then renders the user's Jinja template into the display value."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, TemplateError
from homeassistant.helpers.template import Template
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import InvestecApiError, InvestecAuthError, InvestecClient
from .budget import budget_period, simplify_transaction, spend_between, validate_display
from .const import (CONF_ACCOUNTS, CONF_CUSTOM_VARIABLES, CONF_PAYDAY, CONF_TEMPLATE, CONF_WEEKEND_SHIFT,
                    DEFAULT_PAYDAY,
                    DEFAULT_SCAN_INTERVAL, DEFAULT_TEMPLATE, DEFAULT_TEST_BALANCE, DOMAIN,
                    EXCLUDED_TRANSACTION_TYPES)

_LOGGER = logging.getLogger(__name__)
MAX_HISTORY_DAYS = 35


@dataclass
class DisplayResult:
    value: str                       # What goes to the screen (always <= 4 characters)
    error: str | None                # Why it is Err, if it is
    raw: str                         # Exactly what the template returned
    variables: dict[str, Any] = field(default_factory=dict)
    custom: dict[str, Any] = field(default_factory=dict)          # name -> value of each user variable
    custom_errors: dict[str, str] = field(default_factory=dict)   # name -> error, for variables that failed


class InvestecBudgetCoordinator(DataUpdateCoordinator[DisplayResult]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: InvestecClient) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=DEFAULT_SCAN_INTERVAL, config_entry=entry)
        self.client = client
        self.accounts: list[dict[str, Any]] = []
        # Test function: a made-up balance used instead of the real one.
        self.test_mode = False
        self.test_balance = DEFAULT_TEST_BALANCE
        self._fetched: dict[str, Any] | None = None
        self.diagnostics: dict[str, Any] = {}
        self.last_options: dict[str, Any] = {}

    # ---------- template ----------

    def _variables(self) -> dict[str, Any]:
        """Built-in template variables. Keep the keys in step with budget.VARIABLE_DESCRIPTIONS."""
        f = self._fetched or {}
        today: date = f.get("today") or dt_util.now().date()
        opts = self.config_entry.options
        start, next_start = budget_period(today, int(opts.get(CONF_PAYDAY, DEFAULT_PAYDAY)),
                                          bool(opts.get(CONF_WEEKEND_SHIFT, True)))
        live_balance = float(f.get("balance", 0.0))
        return {
            "balance": self.test_balance if self.test_mode else live_balance,
            "live_balance": live_balance,
            "test_mode": self.test_mode,
            "accounts": f.get("accounts", []),
            "transactions": f.get("transactions", []),
            "spent_today": f.get("spent_today", 0.0),
            "spent_cycle": f.get("spent_cycle", 0.0),
            "days_to_payday": max((next_start - today).days, 1),   # Today included
            "cycle_start": start.isoformat(),
            "payday": next_start.isoformat(),
            "today": today.isoformat(),
        }

    def _with_custom(self, variables: dict[str, Any], custom_defs: list[dict[str, str]]
                     ) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
        """Add the user's variables in order, so each one can use the ones before it."""
        values: dict[str, Any] = {}
        errors: dict[str, str] = {}
        merged = dict(variables)
        for item in custom_defs:
            name = item["name"]
            try:
                # parse_result=True turns "123.4" into a number and "[...]" into a list.
                value = Template(item["template"], self.hass).async_render(merged, parse_result=True)
            except Exception as err:  # Template or maths error: the variable becomes none.
                value = None
                errors[name] = str(err) if isinstance(err, TemplateError) else repr(err)
            merged[name] = value
            values[name] = value
        return merged, values, errors

    @property
    def custom_variables(self) -> list[dict[str, str]]:
        return list(self.config_entry.options.get(CONF_CUSTOM_VARIABLES) or [])

    def render_source(self, source: str, custom_defs: list[dict[str, str]] | None = None) -> DisplayResult:
        """Render any template against the last fetched data. Used for the saved script and previews."""
        base = self._variables()
        defs = self.custom_variables if custom_defs is None else custom_defs
        variables, custom, custom_errors = self._with_custom(base, defs)
        try:
            raw = Template(source, self.hass).async_render(variables, parse_result=False)
        except TemplateError as err:
            return DisplayResult("Err", f"Template error: {err}", "", base, custom, custom_errors)
        except Exception as err:  # Any maths error inside the template (e.g. division by zero).
            return DisplayResult("Err", f"Template error: {err!r}", "", base, custom, custom_errors)
        value, error = validate_display(raw)
        return DisplayResult(value, error, str(raw).strip()[:100], base, custom, custom_errors)

    @property
    def template_source(self) -> str:
        return self.config_entry.options.get(CONF_TEMPLATE) or DEFAULT_TEMPLATE

    def _render(self) -> DisplayResult:
        return self.render_source(self.template_source)

    def recalculate(self) -> None:
        """Re-render with the last fetched data (no API call). Used by the test controls."""
        if self._fetched is not None:
            self.async_set_updated_data(self._render())

    # ---------- fetch ----------

    async def _async_update_data(self) -> DisplayResult:
        today = dt_util.now().date()  # Home Assistant time zone (set it to Africa/Johannesburg).
        opts = self.config_entry.options
        start, _ = budget_period(today, int(opts.get(CONF_PAYDAY, DEFAULT_PAYDAY)),
                                 bool(opts.get(CONF_WEEKEND_SHIFT, True)))
        # From the start of the pay cycle (at most 35 days), a few days earlier for late postings.
        since = max(start, today - timedelta(days=MAX_HISTORY_DAYS)) - timedelta(days=3)
        try:
            if not self.accounts:
                self.accounts = await self.client.accounts()
            names = {a["accountId"]: (a.get("referenceName") or a.get("accountName") or "Account")
                     for a in self.accounts}
            selected = opts.get(CONF_ACCOUNTS) or list(names)

            # All accounts in parallel; Investec's transactions endpoint can take 20-40 s per account.
            async def fetch(account_id: str) -> tuple[float, list[dict[str, Any]]]:
                bal = await self.client.available_balance(account_id)
                rows = await self.client.transactions(account_id, since, today + timedelta(days=1))
                return bal, rows

            results = await asyncio.gather(*(fetch(a) for a in selected), return_exceptions=True)
        except InvestecAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except InvestecApiError as err:
            _LOGGER.warning("Investec API update failed: %s", err)
            raise UpdateFailed(f"Investec API: {err}") from err

        balance = 0.0
        raw_rows: list[dict[str, Any]] = []
        accounts: list[dict[str, Any]] = []
        transactions: list[dict[str, Any]] = []
        failed: list[str] = []
        for account_id, res in zip(selected, results):
            if isinstance(res, InvestecAuthError):
                raise ConfigEntryAuthFailed(str(res)) from res
            if isinstance(res, BaseException):
                failed.append(account_id[-4:])
                _LOGGER.warning("Investec account ...%s skipped this update: %s", account_id[-4:], res)
                continue
            label = f"{names.get(account_id, 'Account')} ...{account_id[-4:]}"
            balance += res[0]
            accounts.append({"name": label, "balance": round(res[0], 2)})
            raw_rows.extend(res[1])
            transactions.extend(simplify_transaction(t, label) for t in res[1])
        if selected and len(failed) == len(selected):
            raise UpdateFailed("Investec API: all selected accounts failed")

        transactions.sort(key=lambda t: t["date"], reverse=True)
        self._fetched = {
            "today": today,
            "balance": round(balance, 2),
            "accounts": accounts,
            "transactions": transactions,
            "spent_today": spend_between(raw_rows, today, today, EXCLUDED_TRANSACTION_TYPES),
            "spent_cycle": spend_between(raw_rows, start, today, EXCLUDED_TRANSACTION_TYPES),
        }
        # Diagnostics (counts only; no descriptions or merchant names).
        self.diagnostics = {
            "transactions_fetched": len(transactions),
            "transactions_dated_today": sum(1 for t in transactions if t["date"] == today.isoformat()),
            "accounts_skipped": failed,
            "last_fetch": dt_util.now().isoformat(timespec="seconds"),
        }
        return self._render()
