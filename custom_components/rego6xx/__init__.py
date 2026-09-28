"""Rego 6XX."""

from __future__ import annotations

from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Rego6xxApi, Rego6xxApiError, Rego6xxAuthError
from .coordinator import Rego6xxConfigEntry, Rego6xxCoordinator

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.BUTTON,
]


async def async_setup_entry(hass: HomeAssistant, entry: Rego6xxConfigEntry) -> bool:
    api = Rego6xxApi(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data.get(CONF_API_KEY, ""),
    )
    try:
        info = await api.async_info()
    except Rego6xxAuthError as err:
        raise ConfigEntryAuthFailed from err
    except Rego6xxApiError as err:
        raise ConfigEntryNotReady(f"Kan inte nå enheten: {err}") from err

    coordinator = Rego6xxCoordinator(hass, entry, api, info)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Rego6xxConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: Rego6xxConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
