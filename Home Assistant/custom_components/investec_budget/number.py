"""Test balance: a made-up bank balance used instead of the real one while Test mode is on."""
from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import InvestecBudgetCoordinator
from .entity import device_info


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([TestBalanceNumber(entry.runtime_data, entry)])


class TestBalanceNumber(RestoreNumber):
    _attr_has_entity_name = True
    _attr_name = "Test balance"
    _attr_icon = "mdi:cash-edit"
    _attr_device_class = NumberDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "ZAR"
    _attr_native_min_value = 0
    _attr_native_max_value = 10_000_000
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: InvestecBudgetCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_test_balance"
        self._attr_device_info = device_info(entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last and last.native_value is not None:
            self._coordinator.test_balance = float(last.native_value)
            self._coordinator.recalculate()

    @property
    def native_value(self) -> float:
        return self._coordinator.test_balance

    async def async_set_native_value(self, value: float) -> None:
        self._coordinator.test_balance = float(value)
        self._coordinator.recalculate()
        self.async_write_ha_state()
