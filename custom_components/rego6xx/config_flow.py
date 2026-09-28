"""Config flow: host, port, API-nyckel. Valideras med /health + /info."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Rego6xxApi, Rego6xxAuthError, Rego6xxApiError, Rego6xxConnectionError
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import Rego6xxConfigEntry


async def _validate(hass: HomeAssistant, host: str, port: int, api_key: str) -> dict[str, Any]:
    """Kontrollera /health och hämta /info. Kastar Rego6xxApiError vid fel."""
    api = Rego6xxApi(async_get_clientsession(hass), host, port, api_key)
    await api.async_health()
    return await api.async_info()


def _error_key(err: Exception) -> str:
    if isinstance(err, Rego6xxAuthError):
        return "invalid_auth"
    if isinstance(err, Rego6xxConnectionError):
        return "cannot_connect"
    return "unknown"


class Rego6xxConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host, port = user_input[CONF_HOST], user_input[CONF_PORT]
            try:
                info = await _validate(
                    self.hass, host, port, user_input.get(CONF_API_KEY, "")
                )
            except Rego6xxApiError as err:
                errors["base"] = _error_key(err)
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(str(info.get("serial") or f"{host}:{port}"))
                self._abort_if_unique_id_configured(updates=user_input)
                return self.async_create_entry(
                    title=str(info.get("name") or host), data=user_input
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Optional(CONF_API_KEY, default=""): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                await _validate(
                    self.hass,
                    entry.data[CONF_HOST],
                    entry.data[CONF_PORT],
                    user_input[CONF_API_KEY],
                )
            except Rego6xxApiError as err:
                errors["base"] = _error_key(err)
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: user_input[CONF_API_KEY]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Rego6xxConfigEntry) -> OptionsFlow:
        return Rego6xxOptionsFlow()


class Rego6xxOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    )
                }
            ),
        )
