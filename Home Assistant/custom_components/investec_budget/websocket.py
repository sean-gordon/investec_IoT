"""Websocket commands used by the Investec Display sidebar page (admin only)."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.template import Template

from .budget import VARIABLE_DESCRIPTIONS, validate_custom_variables
from .const import CONF_CUSTOM_VARIABLES, CONF_TEMPLATE, DOMAIN
from .coordinator import InvestecBudgetCoordinator
from .examples import EXAMPLES, VARIABLE_SUGGESTIONS


@callback
def async_register(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_state)
    websocket_api.async_register_command(hass, ws_preview)
    websocket_api.async_register_command(hass, ws_save)


def _coordinator(hass: HomeAssistant, entry_id: str | None) -> InvestecBudgetCoordinator | None:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED and (entry_id is None or entry.entry_id == entry_id):
            return entry.runtime_data
    return None


def _result(r: Any) -> dict[str, Any]:
    return {"value": r.value, "error": r.error, "raw": r.raw,
            "custom": r.custom, "custom_errors": r.custom_errors}


def _check(hass: HomeAssistant, source: str | None, custom: Any) -> tuple[list[dict[str, str]] | None, str | None]:
    """Validate variable definitions and template syntax. Returns (clean variables, error)."""
    clean, err = validate_custom_variables(custom)
    if err:
        return None, err
    for item in clean:
        try:
            Template(item["template"], hass).ensure_valid()
        except TemplateError as exc:
            return None, f"Variable '{item['name']}': syntax error: {exc}"
    if source is not None:
        try:
            Template(source, hass).ensure_valid()
        except TemplateError as exc:
            return None, f"Display script: syntax error: {exc}"
    return clean, None


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/state", vol.Optional("entry_id"): str})
@callback
def ws_state(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    coord = _coordinator(hass, msg.get("entry_id"))
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Investec Display is not loaded yet. Try again shortly.")
        return
    entry = coord.config_entry
    reg = er.async_get(hass)
    entities = {key: reg.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
                for platform, key in (("switch", "test_mode"), ("number", "test_balance"),
                                      ("sensor", "display_value"))}
    data = coord.data
    connection.send_result(msg["id"], {
        "entry_id": entry.entry_id,
        "template": coord.template_source,
        "custom_variables": coord.custom_variables,
        "variable_suggestions": VARIABLE_SUGGESTIONS,
        "variable_descriptions": VARIABLE_DESCRIPTIONS,
        "current": _result(data) if data else None,
        "variables": data.variables if data else {},
        "test_mode": coord.test_mode,
        "test_balance": coord.test_balance,
        "entities": entities,
        "diagnostics": coord.diagnostics,
        "examples": EXAMPLES,
    })


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/preview", vol.Required("template"): str,
                                  vol.Optional("custom_variables"): list, vol.Optional("entry_id"): str})
@callback
def ws_preview(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    coord = _coordinator(hass, msg.get("entry_id"))
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Investec Display is not loaded yet.")
        return
    custom = msg.get("custom_variables")
    if custom is None:
        connection.send_result(msg["id"], _result(coord.render_source(msg["template"])))
        return
    clean, err = validate_custom_variables(custom)
    if err:  # Show the problem in the preview rather than failing the call.
        connection.send_result(msg["id"], {"value": "Err", "error": err, "raw": "", "custom": {},
                                           "custom_errors": {}})
        return
    connection.send_result(msg["id"], _result(coord.render_source(msg["template"], clean)))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/save", vol.Required("template"): str,
                                  vol.Optional("custom_variables"): list, vol.Optional("entry_id"): str})
@callback
def ws_save(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    coord = _coordinator(hass, msg.get("entry_id"))
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Investec Display is not loaded yet.")
        return
    source = msg["template"]
    custom = msg.get("custom_variables", coord.custom_variables)
    clean, err = _check(hass, source, custom)
    if err:
        connection.send_error(msg["id"], "invalid", err)
        return
    entry = coord.config_entry
    # Script and variable changes are applied without reloading (see __init__._options_updated).
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_TEMPLATE: source, CONF_CUSTOM_VARIABLES: clean})
    connection.send_result(msg["id"], _result(coord.render_source(source, clean)))
