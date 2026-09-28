"""Binärsensorer: binary_sensors, leds och seriell anslutning."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import Rego6xxConfigEntry, Rego6xxCoordinator
from .entity import Rego6xxEntity, setup_dynamic

DEVICE_CLASSES = {
    "alarm": BinarySensorDeviceClass.PROBLEM,
    "compressor": BinarySensorDeviceClass.RUNNING,
    "radiator_pump_p1": BinarySensorDeviceClass.RUNNING,
    "heat_carrier_pump_p2": BinarySensorDeviceClass.RUNNING,
    "ground_loop_pump_p3": BinarySensorDeviceClass.RUNNING,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Rego6xxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    setup_dynamic(
        entry,
        async_add_entities,
        {
            "binary_sensors": Rego6xxBinarySensor,
            "leds": Rego6xxBinarySensor,
            "connection": Rego6xxBinarySensor,
        },
    )


class Rego6xxBinarySensor(Rego6xxEntity, BinarySensorEntity):
    def __init__(
        self, coordinator: Rego6xxCoordinator, group: str, key: str, slug: str
    ) -> None:
        super().__init__(coordinator, group, key, slug)
        if group in ("leds", "connection"):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if group == "connection":
            self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        elif group == "binary_sensors":
            self._attr_device_class = DEVICE_CLASSES.get(key)

    @property
    def is_on(self) -> bool | None:
        value = self.item.get("value")
        return None if value is None else bool(value)
