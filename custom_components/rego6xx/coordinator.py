"""DataUpdateCoordinator som pollar /status."""

from __future__ import annotations

from collections.abc import Awaitable
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Rego6xxApi, Rego6xxApiError, Rego6xxAuthError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type Rego6xxConfigEntry = ConfigEntry[Rego6xxCoordinator]
type StatusData = dict[str, dict[str, dict[str, Any]]]


class Rego6xxCoordinator(DataUpdateCoordinator[StatusData]):
    """Hämtar /status och delar en gemensam DeviceInfo (från /info)."""

    config_entry: Rego6xxConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: Rego6xxConfigEntry,
        api: Rego6xxApi,
        info: dict[str, Any],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.api = api
        self.info = info
        host, port = entry.data[CONF_HOST], entry.data[CONF_PORT]
        kw = info.get("pump_size_kw")
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=str(info.get("model") or f"Rego 6XX {host}"),
            manufacturer=str(info.get("manufacturer") or "IVT/Bosch"),
            model=f"Rego 600, {kw} kW" if kw else "Rego 600",
            sw_version=str(info["version"]) if info.get("version") else None,
            configuration_url=f"http://{host}:{port}",
        )

    async def _async_update_data(self) -> StatusData:
        try:
            return await self.api.async_status()
        except Rego6xxAuthError as err:
            raise ConfigEntryAuthFailed from err
        except Rego6xxApiError as err:
            raise UpdateFailed(f"Kunde inte hämta /status: {err}") from err

    async def async_write(self, call: Awaitable[None]) -> None:
        """Utför en POST och uppdatera direkt efteråt."""
        try:
            await call
        except Rego6xxApiError as err:
            raise HomeAssistantError(f"Skrivning misslyckades: {err}") from err
        await self.async_request_refresh()
