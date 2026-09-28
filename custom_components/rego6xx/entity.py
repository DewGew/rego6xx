"""Gemensam basentitet och dynamisk entitetsregistrering."""

from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import Rego6xxConfigEntry, Rego6xxCoordinator

# Grupper som delar plattform med en annan grupp får prefix i sluggen
# så att unique_id inte kolliderar (sensors/power/energy, binary_sensors/leds).
_PREFIXED = ("power", "energy", "leds")


def make_slug(group: str, key: str) -> str:
    return f"{group}_{key}" if group in _PREFIXED else key


class Rego6xxEntity(CoordinatorEntity[Rego6xxCoordinator]):
    """Bas: unique_id = {entry_id}_{slug}, gemensam DeviceInfo."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: Rego6xxCoordinator, group: str, key: str, slug: str
    ) -> None:
        super().__init__(coordinator)
        self._group = group
        self._key = key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{slug}"
        self._attr_device_info = coordinator.device_info
        self._attr_name = str(self.item.get("name") or key)

    @property
    def item(self) -> dict[str, Any]:
        return self.coordinator.data.get(self._group, {}).get(self._key, {})

    @property
    def available(self) -> bool:
        return super().available and self._key in self.coordinator.data.get(self._group, {})


def setup_dynamic(
    entry: Rego6xxConfigEntry,
    async_add_entities: AddEntitiesCallback,
    groups: dict[str, type[Rego6xxEntity]],
) -> None:
    """Skapa entiteter för alla poster i /status, även sådana som dyker upp senare."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add() -> None:
        new: list[Rego6xxEntity] = []
        for group, cls in groups.items():
            for key in coordinator.data.get(group, {}):
                slug = make_slug(group, key)
                if slug not in known:
                    known.add(slug)
                    new.append(cls(coordinator, group, key, slug))
        if new:
            async_add_entities(new)

    _add()
    entry.async_on_unload(coordinator.async_add_listener(_add))
