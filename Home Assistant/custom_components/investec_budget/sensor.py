"""Sensors: the display value produced by your template, plus a few inputs for reference."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import DisplayResult, InvestecBudgetCoordinator
from .entity import device_info


@dataclass(frozen=True, kw_only=True)
class InvestecSensorDescription(SensorEntityDescription):
    value: Callable[[DisplayResult], Any]


SENSORS = (
    InvestecSensorDescription(key="display_value", name="Display value", icon="mdi:numeric",
                              value=lambda r: r.value),
    InvestecSensorDescription(key="balance", name="Balance", device_class=SensorDeviceClass.MONETARY,
                              native_unit_of_measurement="ZAR", value=lambda r: r.variables.get("balance")),
    InvestecSensorDescription(key="spent_today", name="Spent today", device_class=SensorDeviceClass.MONETARY,
                              native_unit_of_measurement="ZAR", value=lambda r: r.variables.get("spent_today")),
    InvestecSensorDescription(key="days_left", name="Days to payday", native_unit_of_measurement=UnitOfTime.DAYS,
                              icon="mdi:calendar-clock", value=lambda r: r.variables.get("days_to_payday")),
    InvestecSensorDescription(key="mode", name="Budget mode", icon="mdi:test-tube",
                              device_class=SensorDeviceClass.ENUM, options=["live", "test"],
                              value=lambda r: "test" if r.variables.get("test_mode") else "live"),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: InvestecBudgetCoordinator = entry.runtime_data
    async_add_entities(InvestecSensor(coordinator, entry, d) for d in SENSORS)


class InvestecSensor(CoordinatorEntity[InvestecBudgetCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: InvestecSensorDescription

    def __init__(self, coordinator: InvestecBudgetCoordinator, entry: ConfigEntry,
                 description: InvestecSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = device_info(entry)

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        if self.entity_description.key == "display_value":
            return {"error": data.error, "template_output": data.raw}
        if self.entity_description.key == "spent_today":
            return self.coordinator.diagnostics
        return None
