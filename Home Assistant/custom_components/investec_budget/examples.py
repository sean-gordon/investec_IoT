"""Example display scripts offered in the Investec Display page."""
from .const import DEFAULT_TEMPLATE

EXAMPLES: list[dict[str, str]] = [
    {
        "name": "Daily budget used (%)",
        "description": "Today's spend as a % of the daily budget. Under 100 is on track.",
        "template": DEFAULT_TEMPLATE,
    },
    {
        "name": "Rand left today",
        "description": "Rand left to spend today, e.g. 850. OVER once you pass the budget. Shows 9999 above R9 999.",
        "template": """{% set left = (balance + spent_today) / days_to_payday - spent_today %}
{% if left < 0 %}OVER{% else %}{{ [left | round | int, 9999] | min }}{% endif %}""",
    },
    {
        "name": "Traffic light word",
        "description": "GOOD under 80%, HIGH up to 100%, OVER beyond.",
        "template": """{% set pct = spent_today / ((balance + spent_today) / days_to_payday) * 100 %}
{{ 'GOOD' if pct < 80 else ('HIGH' if pct <= 100 else 'OVER') }}""",
    },
    {
        "name": "Days to payday",
        "description": "Days left until payday, today included.",
        "template": "{{ days_to_payday }}",
    },
    {
        "name": "Cycle pace (%)",
        "description": "Spend this cycle against an even spread. 100 is on pace.",
        "template": """{% set cycle_days = (as_datetime(payday) - as_datetime(cycle_start)).days %}
{% set days_gone = cycle_days - days_to_payday + 1 %}
{% set started_with = balance + spent_cycle %}
{% set expected = started_with / cycle_days * days_gone %}
{{ [(spent_cycle / expected * 100) | round | int, 9999] | min if expected > 0 else 0 }}""",
    },
    {
        "name": "Balance in thousands",
        "description": "Available balance in thousands with a t, e.g. 8.6t for R8 600 or 23t for R23 446. OVER when negative.",
        "template": "{% if balance < 0 %}OVER{% elif balance >= 1000 %}{{ (('%.2f' | format(balance / 1000))[:3]).rstrip('.') }}t{% else %}{{ balance | round | int }}{% endif %}",
    },
    {
        "name": "Purchases today",
        "description": "Number of debit transactions today.",
        "template": "{{ transactions | selectattr('date', 'eq', today) | selectattr('type', 'eq', 'DEBIT') | list | count }}",
    },
    {
        "name": "Spend at one shop today",
        "description": "Change WOOLWORTHS to part of any merchant name.",
        "template": "{{ transactions | selectattr('date', 'eq', today) | selectattr('description', 'search', 'WOOLWORTHS') | map(attribute='amount') | sum | round | int }}",
    },
    {
        "name": "No-spend day streak",
        "description": "Days in a row, before today, without card purchases.",
        "template": """{% set ns = namespace(n=0, stop=false) %}
{% for i in range(1, 31) %}
  {% set d = (as_datetime(today) - timedelta(days=i)).strftime('%Y-%m-%d') %}
  {% if not ns.stop %}
    {% if transactions | selectattr('date', 'eq', d) | selectattr('transaction_type', 'eq', 'CardPurchases') | list | count == 0 %}
      {% set ns.n = ns.n + 1 %}
    {% else %}
      {% set ns.stop = true %}
    {% endif %}
  {% endif %}
{% endfor %}
{{ ns.n }}""",
    },
    {
        "name": "Day % / night days-to-payday",
        "description": "Daily budget % from 06:00 to 22:00, days to payday overnight.",
        "template": """{% if 6 <= now().hour < 22 %}
  {{ (spent_today / ((balance + spent_today) / days_to_payday) * 100) | round | int }}
{% else %}
  {{ days_to_payday }}
{% endif %}""",
    },
]

# Ready-made variables offered on the page ("Add a suggested variable").
VARIABLE_SUGGESTIONS: list[dict[str, str]] = [
    {"name": "start_of_day", "description": "Balance at the start of today",
     "template": "{{ balance + spent_today }}"},
    {"name": "daily_budget", "description": "What you can spend per day until payday",
     "template": "{{ (balance + spent_today) / days_to_payday }}"},
    {"name": "left_today", "description": "Money left for today (negative when over)",
     "template": "{{ (balance + spent_today) / days_to_payday - spent_today }}"},
    {"name": "pct_today", "description": "Today's spend as a % of the daily budget",
     "template": "{{ (spent_today / ((balance + spent_today) / days_to_payday) * 100) | round(1) if balance + spent_today > 0 else 0 }}"},
    {"name": "cycle_days", "description": "Length of this pay cycle in days",
     "template": "{{ (as_datetime(payday) - as_datetime(cycle_start)).days }}"},
    {"name": "days_gone", "description": "Days of this cycle already gone, today included",
     "template": "{{ (as_datetime(payday) - as_datetime(cycle_start)).days - days_to_payday + 1 }}"},
    {"name": "avg_per_day", "description": "Average spend per day so far this cycle",
     "template": "{{ (spent_cycle / ((as_datetime(payday) - as_datetime(cycle_start)).days - days_to_payday + 1)) | round(2) }}"},
    {"name": "pending_total", "description": "Total of pending transactions",
     "template": "{{ transactions | selectattr('status', 'eq', 'PENDING') | map(attribute='amount') | sum | round(2) }}"},
    {"name": "purchases_today", "description": "Number of debit transactions today",
     "template": "{{ transactions | selectattr('date', 'eq', today) | selectattr('type', 'eq', 'DEBIT') | list | count }}"},
    {"name": "biggest_today", "description": "Largest single debit today",
     "template": "{{ (transactions | selectattr('date', 'eq', today) | selectattr('type', 'eq', 'DEBIT') | map(attribute='amount') | list + [0]) | max }}"},
    {"name": "income_cycle", "description": "Money in this cycle, excluding transfers",
     "template": "{{ transactions | selectattr('type', 'eq', 'CREDIT') | selectattr('date', 'ge', cycle_start) | rejectattr('transaction_type', 'eq', 'Transfers') | map(attribute='amount') | sum | round(2) }}"},
    {"name": "groceries_cycle", "description": "Spend at one shop this cycle (edit the name)",
     "template": "{{ transactions | selectattr('type', 'eq', 'DEBIT') | selectattr('date', 'ge', cycle_start) | selectattr('description', 'search', 'WOOLWORTHS') | map(attribute='amount') | sum | round(2) }}"},
]
