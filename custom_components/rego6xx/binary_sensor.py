"""Binärsensorer: binary_sensors och leds."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import Rego6xxConfigEntry, Rego6xxCoordinator
from .entity import Rego6xxEntity, setup_dynamic


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Rego6xxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    setup_dynamic(
        entry,
        async_add_entities,
        {"binary_sensors": Rego6xxBinarySensor, "leds": Rego6xxBinarySensor},
    )


class Rego6xxBinarySensor(Rego6xxEntity, BinarySensorEntity):
    def __init__(
        self, coordinator: Rego6xxCoordinator, group: str, key: str, slug: str
    ) -> None:
        super().__init__(coordinator, group, key, slug)
        if group == "leds":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool | None:
        value = self.item.get("value")
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "on", "yes")
        return bool(value)
