"""Config and options flow: API keys and the display template are entered in the Home Assistant UI."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import selector
from homeassistant.helpers.template import Template

from .api import InvestecApiError, InvestecAuthError, InvestecClient
from .const import (CONF_ACCOUNTS, CONF_API_KEY, CONF_CLIENT_ID, CONF_CLIENT_SECRET,
                    CONF_PAYDAY, CONF_SANDBOX, CONF_TEMPLATE, CONF_WEEKEND_SHIFT, DEFAULT_PAYDAY,
                    DEFAULT_TEMPLATE, DOMAIN)


def _account_label(a: dict[str, Any]) -> str:
    name = a.get("referenceName") or a.get("accountName") or "Account"
    number = str(a.get("accountNumber") or "")
    return f"{name} ({a.get('productName', '')} ...{number[-4:]})"


def _settings_schema(accounts: list[dict[str, Any]], defaults: dict[str, Any]) -> vol.Schema:
    options = [selector.SelectOptionDict(value=a["accountId"], label=_account_label(a)) for a in accounts]
    return vol.Schema({
        vol.Required(CONF_ACCOUNTS, default=defaults.get(CONF_ACCOUNTS, [o["value"] for o in options])):
            selector.SelectSelector(selector.SelectSelectorConfig(options=options, multiple=True)),
        vol.Required(CONF_PAYDAY, default=defaults.get(CONF_PAYDAY, DEFAULT_PAYDAY)):
            selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=31, step=1,
                                                                  mode=selector.NumberSelectorMode.BOX)),
        vol.Required(CONF_WEEKEND_SHIFT, default=defaults.get(CONF_WEEKEND_SHIFT, True)): bool,
        # The display script: a Jinja template that must return 4 characters or fewer.
        vol.Required(CONF_TEMPLATE, default=defaults.get(CONF_TEMPLATE, DEFAULT_TEMPLATE)):
            selector.TemplateSelector(),
    })


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    return {**user_input, CONF_PAYDAY: int(user_input[CONF_PAYDAY])}


def _template_error(hass: Any, source: str) -> str | None:
    """Syntax check only; the result is checked every time it renders."""
    try:
        Template(source, hass).ensure_valid()
    except TemplateError:
        return "invalid_template"
    return None


class InvestecBudgetConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._credentials: dict[str, Any] = {}
        self._accounts: list[dict[str, Any]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = InvestecClient(async_get_clientsession(self.hass), user_input[CONF_CLIENT_ID],
                                    user_input[CONF_CLIENT_SECRET], user_input[CONF_API_KEY],
                                    user_input.get(CONF_SANDBOX, False))
            try:
                self._accounts = await client.accounts()
            except InvestecAuthError:
                errors["base"] = "invalid_auth"
            except InvestecApiError:
                errors["base"] = "cannot_connect"
            else:
                if not self._accounts:
                    errors["base"] = "no_accounts"
                else:
                    await self.async_set_unique_id(user_input[CONF_CLIENT_ID])
                    self._abort_if_unique_id_configured()
                    self._credentials = user_input
                    return await self.async_step_settings()
        return self.async_show_form(step_id="user", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_CLIENT_ID): str,
            vol.Required(CONF_CLIENT_SECRET): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            vol.Required(CONF_API_KEY): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            vol.Optional(CONF_SANDBOX, default=False): bool,
        }))

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not (err := _template_error(self.hass, user_input[CONF_TEMPLATE])):
                return self.async_create_entry(title="Investec Display", data=self._credentials,
                                               options=_clean(user_input))
            errors[CONF_TEMPLATE] = err
        return self.async_show_form(step_id="settings", errors=errors,
                                    data_schema=_settings_schema(self._accounts, user_input or {}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return InvestecBudgetOptionsFlow()


class InvestecBudgetOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not (err := _template_error(self.hass, user_input[CONF_TEMPLATE])):
                # Keep options the form does not show (e.g. custom variables from the page).
                return self.async_create_entry(data={**self.config_entry.options, **_clean(user_input)})
            errors[CONF_TEMPLATE] = err
        coordinator = getattr(self.config_entry, "runtime_data", None)
        accounts = coordinator.accounts if coordinator and coordinator.accounts else []
        if not accounts:  # Integration not loaded yet: ask Investec directly.
            data = self.config_entry.data
            client = InvestecClient(async_get_clientsession(self.hass), data[CONF_CLIENT_ID],
                                    data[CONF_CLIENT_SECRET], data[CONF_API_KEY], data.get(CONF_SANDBOX, False))
            try:
                accounts = await client.accounts()
            except (InvestecApiError, InvestecAuthError):
                return self.async_abort(reason="cannot_connect")
        return self.async_show_form(step_id="init", errors=errors,
                                    data_schema=_settings_schema(accounts, user_input or dict(self.config_entry.options)))
