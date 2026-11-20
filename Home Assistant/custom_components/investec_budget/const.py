"""Constants for the Investec Display integration."""
from datetime import timedelta

DOMAIN = "investec_budget"

CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_API_KEY = "api_key"
CONF_SANDBOX = "sandbox"
CONF_ACCOUNTS = "accounts"
CONF_PAYDAY = "payday"
CONF_WEEKEND_SHIFT = "weekend_shift"
CONF_TEMPLATE = "template"
CONF_CUSTOM_VARIABLES = "custom_variables"

PROD_BASE = "https://openapi.investec.com"
SANDBOX_BASE = "https://openapisandbox.investec.com"

DEFAULT_PAYDAY = 25
DEFAULT_SCAN_INTERVAL = timedelta(minutes=10)
DEFAULT_TEST_BALANCE = 10000.0

# Default display script: today's spend as a % of a daily budget
# (balance at the start of today divided by days left until payday).
DEFAULT_TEMPLATE = """{% set start_of_day = balance + spent_today %}
{% set daily_budget = start_of_day / days_to_payday %}
{% if daily_budget > 0 %}{{ (spent_today / daily_budget * 100) | round | int }}{% else %}0{% endif %}"""

# Debits with these transaction types move money between your own accounts,
# so spent_today / spent_cycle leave them out. Raw transactions keep them.
EXCLUDED_TRANSACTION_TYPES = {"Transfers"}
