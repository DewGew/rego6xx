"""Number: settings. min/max/step läses ur /status-svaret."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity
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
    setup_dynamic(entry, async_add_entities, {"settings": Rego6xxNumber})


class Rego6xxNumber(Rego6xxEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: Rego6xxCoordinator, group: str, key: str, slug: str
    ) -> None:
        super().__init__(coordinator, group, key, slug)
        self._attr_native_unit_of_measurement = self.item.get("unit")

    def _num(self, field: str, default: float) -> float:
        value: Any = self.item.get(field)
        try:
            return float(value) if value is not None else default
        except (TypeError, ValueError):
            return default

    @property
    def native_min_value(self) -> float:
        return self._num("min", 0)

    @property
    def native_max_value(self) -> float:
        return self._num("max", 100)

    @property
    def native_step(self) -> float:
        return self._num("step", 1)

    @property
    def native_value(self) -> float | None:
        value = self.item.get("value")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        payload: float | int = int(value) if float(value).is_integer() else value
        await self.coordinator.async_write(
            self.coordinator.api.async_set_setting(self._key, payload)
        )
