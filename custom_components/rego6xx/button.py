"""Knappar: keys (frontpanelens knappar)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import Rego6xxConfigEntry
from .entity import Rego6xxEntity, setup_dynamic


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Rego6xxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    setup_dynamic(entry, async_add_entities, {"keys": Rego6xxButton})


class Rego6xxButton(Rego6xxEntity, ButtonEntity):
    async def async_press(self) -> None:
        await self.coordinator.async_write(self.coordinator.api.async_press_key(self._key))
