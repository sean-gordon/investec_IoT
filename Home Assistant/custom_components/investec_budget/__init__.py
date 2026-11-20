"""Investec Display: Investec data in, your Jinja template decides what the 4-digit screen shows."""
from __future__ import annotations

import json
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from . import websocket
from .api import InvestecClient
from .const import CONF_API_KEY, CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_SANDBOX, CONF_TEMPLATE, CONF_CUSTOM_VARIABLES, DOMAIN
from .coordinator import InvestecBudgetCoordinator

PLATFORMS = [Platform.SENSOR, Platform.NUMBER, Platform.SWITCH]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PANEL_URL = "investec-display"
STATIC_URL = "/investec_budget_static"
_VERSION = json.loads((Path(__file__).parent / "manifest.json").read_text())["version"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the sidebar page's websocket commands and static files once."""
    websocket.async_register(hass)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "www"), False)])
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = InvestecClient(async_get_clientsession(hass), entry.data[CONF_CLIENT_ID],
                            entry.data[CONF_CLIENT_SECRET], entry.data[CONF_API_KEY],
                            entry.data.get(CONF_SANDBOX, False))
    coordinator = InvestecBudgetCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    coordinator.last_options = dict(entry.options)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_options_updated))

    if PANEL_URL not in hass.data.get("frontend_panels", {}):
        try:
            await panel_custom.async_register_panel(
                hass,
                frontend_url_path=PANEL_URL,
                webcomponent_name="investec-display-panel",
                module_url=f"{STATIC_URL}/panel.js?v={_VERSION}",
                sidebar_title="Investec Display",
                sidebar_icon="mdi:cash-multiple",
                require_admin=True,
                config={"entry_id": entry.entry_id},
            )
        except ValueError:
            pass  # Already registered (e.g. after a reload).
    return True


async def _options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """A new display script or variables only need a re-render; other settings need fresh data."""
    coordinator: InvestecBudgetCoordinator = entry.runtime_data
    render_only = (CONF_TEMPLATE, CONF_CUSTOM_VARIABLES)
    old = {k: v for k, v in coordinator.last_options.items() if k not in render_only}
    new = {k: v for k, v in entry.options.items() if k not in render_only}
    coordinator.last_options = dict(entry.options)
    if old == new:
        coordinator.recalculate()
    else:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    others = [e for e in hass.config_entries.async_entries(DOMAIN)
              if e.entry_id != entry.entry_id and e.state is ConfigEntryState.LOADED]
    if unloaded and not others:
        frontend.async_remove_panel(hass, PANEL_URL)
    return unloaded
