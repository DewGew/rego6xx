"""Sensorer: sensors, power, energy och displayrader."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import Rego6xxConfigEntry, Rego6xxCoordinator
from .entity import Rego6xxEntity, setup_dynamic


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Rego6xxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    setup_dynamic(
        entry,
        async_add_entities,
        {
            "sensors": Rego6xxSensor,
            "power": Rego6xxSensor,
            "energy": Rego6xxSensor,
            "display": Rego6xxSensor,
        },
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
        elif group == "display":
            # Textrader från pumpens display, av som standard
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_entity_registry_enabled_default = False
        else:
            self._attr_native_unit_of_measurement = unit
            if unit == UnitOfTemperature.CELSIUS:
                self._attr_device_class = SensorDeviceClass.TEMPERATURE
            if _is_number(item.get("value")):
                self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Any:
        return self.item.get("value")
