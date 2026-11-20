"""Test mode: compare the Test balance (not real) against today's REAL spend."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import InvestecBudgetCoordinator
from .entity import device_info


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([TestModeSwitch(entry.runtime_data, entry)])


class TestModeSwitch(SwitchEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_name = "Test mode"
    _attr_icon = "mdi:test-tube"

    def __init__(self, coordinator: InvestecBudgetCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_test_mode"
        self._attr_device_info = device_info(entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state == "on":
            self._coordinator.test_mode = True
            self._coordinator.recalculate()

    @property
    def is_on(self) -> bool:
        return self._coordinator.test_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._set(False)

    def _set(self, on: bool) -> None:
        self._coordinator.test_mode = on
        self._coordinator.recalculate()
        self.async_write_ha_state()
