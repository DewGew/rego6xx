"""Sensorer: sensors, power, energy."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import Rego6xxConfigEntry, Rego6xxCoordinator
from .entity import Rego6xxEntity, setup_dynamic


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _device_class(value: Any) -> SensorDeviceClass | None:
    try:
        return SensorDeviceClass(value) if value else None
    except ValueError:
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Rego6xxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    setup_dynamic(
        entry,
        async_add_entities,
        {"sensors": Rego6xxSensor, "power": Rego6xxSensor, "energy": Rego6xxSensor},
    )


class Rego6xxSensor(Rego6xxEntity, SensorEntity):
    def __init__(
        self, coordinator: Rego6xxCoordinator, group: str, key: str, slug: str
    ) -> None:
        super().__init__(coordinator, group, key, slug)
        item = self.item
        unit = item.get("unit")
        if group == "power":
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_native_unit_of_measurement = unit or UnitOfPower.WATT
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif group == "energy":
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = unit or UnitOfEnergy.KILO_WATT_HOUR
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        else:
            self._attr_device_class = _device_class(item.get("device_class"))
            self._attr_native_unit_of_measurement = unit
            if _is_number(item.get("value")):
                self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Any:
        return self.item.get("value")
