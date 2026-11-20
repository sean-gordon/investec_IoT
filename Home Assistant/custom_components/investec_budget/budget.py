"""Pure helpers (no Home Assistant imports, so they can be tested on their own)."""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any, Iterable

DISPLAY_DIGITS = 4
ERROR_TEXT = "Err"
# Letters ESPHome's TM1637 driver has no shape for; it lights every segment, so they look like 8.
UNDRAWABLE = frozenset("KMXkmqwxz")
MAX_CUSTOM_VARIABLES = 30
# The single list of built-in template variables. The coordinator fills these in, validation
# stops custom variables reusing them, and the sidebar page shows these meanings.
VARIABLE_DESCRIPTIONS: dict[str, str] = {
    "balance": "Available balance of the selected accounts (test balance in test mode)",
    "live_balance": "Real available balance, even in test mode",
    "test_mode": "Whether test mode is on",
    "spent_today": "Debits dated today, less card refunds, excluding transfers",
    "spent_cycle": "Same as spent_today, from the last payday to today",
    "days_to_payday": "Days until payday, today included (never below 1)",
    "today": "Today's date",
    "cycle_start": "Last payday",
    "payday": "Next payday",
    "accounts": "List of accounts, each with name and balance",
    "transactions": "Transactions since the last payday, newest first",
}
BUILT_IN_VARIABLES = frozenset(VARIABLE_DESCRIPTIONS)
# Names Home Assistant templates already use; a variable with one of these names would hide it.
RESERVED_NAMES = frozenset({
    "now", "utcnow", "states", "is_state", "state_attr", "as_datetime", "as_timestamp", "timedelta",
    "range", "namespace", "true", "false", "none", "loop", "self", "this", "float", "int", "min", "max",
})


def payday_for(year: int, month: int, day: int, weekend_shift: bool) -> date:
    """Payday in a month; a day past month end becomes the last day.
    With weekend_shift, Saturday/Sunday paydays move to the Friday before."""
    d = date(year, month, min(day, calendar.monthrange(year, month)[1]))
    if weekend_shift:
        while d.weekday() >= 5:
            d -= timedelta(days=1)
    return d


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    m = year * 12 + (month - 1) + delta
    return m // 12, m % 12 + 1


def budget_period(today: date, day: int, weekend_shift: bool) -> tuple[date, date]:
    """(start, next_start) of the pay cycle containing today. day=1 gives the calendar month."""
    start = payday_for(today.year, today.month, day, weekend_shift)
    if start > today:
        y, m = _add_months(today.year, today.month, -1)
        start = payday_for(y, m, day, weekend_shift)
    y, m = _add_months(start.year, start.month, 1)
    return start, payday_for(y, m, day, weekend_shift)


def tx_date(t: dict[str, Any]) -> str:
    return str(t.get("transactionDate") or t.get("postingDate") or "")[:10]


def spend_between(transactions: Iterable[dict[str, Any]], first: date, last: date,
                  excluded_types: set[str]) -> float:
    """Spend from first to last (inclusive): debits less card refunds; transfers and income ignored."""
    total = 0.0
    lo, hi = first.isoformat(), last.isoformat()
    for t in transactions:
        if not lo <= tx_date(t) <= hi:
            continue
        ttype = t.get("transactionType") or ""
        if ttype in excluded_types:
            continue
        amount = abs(float(t.get("amount") or 0))
        kind = str(t.get("type", "")).upper()
        if kind == "DEBIT":
            total += amount
        elif kind == "CREDIT" and ttype == "CardRefunds":
            total -= amount
    return round(max(total, 0.0), 2)


def simplify_transaction(t: dict[str, Any], account_label: str) -> dict[str, Any]:
    """Plain, template-friendly view of one Investec transaction."""
    return {
        "date": tx_date(t),
        "posting_date": str(t.get("postingDate") or "")[:10],
        "amount": round(abs(float(t.get("amount") or 0)), 2),
        "type": str(t.get("type", "")).upper(),            # DEBIT or CREDIT
        "transaction_type": t.get("transactionType") or "",  # e.g. CardPurchases, DebitOrders
        "status": str(t.get("status", "")).upper(),        # POSTED or PENDING
        "description": t.get("description") or "",
        "account": account_label,
    }


def validate_custom_variables(items: Any) -> tuple[list[dict[str, str]], str | None]:
    """Check user variables: list of {"name", "template"}. Returns (clean list, error or None)."""
    if items is None:
        return [], None
    if not isinstance(items, list):
        return [], "Variables must be a list"
    if len(items) > MAX_CUSTOM_VARIABLES:
        return [], f"At most {MAX_CUSTOM_VARIABLES} variables"
    clean: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        name = str((item or {}).get("name", "")).strip()
        template = str((item or {}).get("template", "")).strip()
        if not name and not template:
            continue  # Ignore empty rows.
        if not name or not (name[0].isalpha() or name[0] == "_") or not all(
                c.isascii() and (c.isalnum() or c == "_") for c in name):
            return [], f"'{name}' is not a valid name. Use letters, digits and _, starting with a letter."
        if name.lower() != name:
            return [], f"'{name}': use lower case names"
        if name in BUILT_IN_VARIABLES:
            return [], f"'{name}' is a built-in variable; pick another name"
        if name in RESERVED_NAMES:
            return [], f"'{name}' is reserved by Home Assistant templates; pick another name"
        if name in seen:
            return [], f"'{name}' is defined twice"
        if not template:
            return [], f"'{name}' has no expression"
        seen.add(name)
        clean.append({"name": name, "template": template})
    return clean, None


def validate_display(raw: Any) -> tuple[str, str | None]:
    """Return (text for the display, error or None).

    Up to four characters, letters or digits (plus space and minus). Full stops
    are allowed and do not use a digit, so 12.34 fits. K, M, X and k, m, q, w, x, z
    cannot be drawn on a seven-segment display. Anything else gives Err.
    """
    text = "" if raw is None else str(raw).strip()
    if not text:
        return ERROR_TEXT, "Template returned nothing"
    for ch in text:
        if not (ch.isascii() and (ch.isalnum() or ch in " -.")):
            return ERROR_TEXT, f"Character {ch!r} cannot be shown"
        if ch in UNDRAWABLE:
            return ERROR_TEXT, f"The display cannot draw {ch!r} (it would show as 8)"
    digits = len(text.replace(".", ""))
    if digits == 0:
        return ERROR_TEXT, "Template returned only full stops"
    if digits > DISPLAY_DIGITS:
        return ERROR_TEXT, f"'{text[:20]}' is {digits} characters; the display fits {DISPLAY_DIGITS}"
    return text, None
