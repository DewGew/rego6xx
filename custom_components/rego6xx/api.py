"""Asynkron HTTP-klient för Rego600 REST API (inga Home Assistant-beroenden)."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import quote

import aiohttp

TIMEOUT = 10
API_KEY_HEADER = "X-API-Key"
API_PREFIX = "/api/v1"

# Knappar finns inte i /status utan är fasta i API:t (POST /api/v1/keys/{key}).
KEYS = {
    "1": "Button 1",
    "2": "Button 2",
    "3": "Button 3",
    "wheel_left": "Wheel left",
    "wheel_right": "Wheel right",
}


class Rego6xxApiError(Exception):
    """Grundfel."""


class Rego6xxConnectionError(Rego6xxApiError):
    """Kunde inte nå API:t."""


class Rego6xxAuthError(Rego6xxApiError):
    """Ogiltig API-nyckel."""


def normalize_group(data: Any) -> dict[str, dict[str, Any]]:
    """Gör om en grupp till {slug: {name, value, ...}}.

    Skalärer blir {"value": x}. Binära poster (``state``) får även ``value``.
    """
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(data, dict):
        return result
    for key, item in data.items():
        entry = dict(item) if isinstance(item, dict) else {"value": item}
        if "value" not in entry and "state" in entry:
            entry["value"] = entry["state"]
        result[str(key)] = entry
    return result


def normalize_status(raw: Any) -> dict[str, dict[str, dict[str, Any]]]:
    """Översätt /api/v1/status till {grupp: {slug: {..}}}."""
    if not isinstance(raw, dict):
        raise Rego6xxApiError("Oväntat svar från /status")
    energy = raw.get("energy_total_kwh")
    return {
        "sensors": normalize_group(raw.get("sensors")),
        "power": normalize_group(raw.get("power")),
        "energy": (
            {"total": {"name": "Total energy", "value": energy}} if energy is not None else {}
        ),
        "display": normalize_group(raw.get("display")),
        "binary_sensors": normalize_group(raw.get("binary_sensors")),
        "leds": normalize_group(raw.get("leds")),
        "connection": {
            "serial": {"name": "Serial connection", "value": bool(raw.get("connected", True))}
        },
        "settings": normalize_group(raw.get("settings")),
        "keys": {key: {"name": name} for key, name in KEYS.items()},
    }


class Rego6xxApi:
    """Klient mot Rego600 REST API."""

    def __init__(
        self, session: aiohttp.ClientSession, host: str, port: int, api_key: str = ""
    ) -> None:
        self._session = session
        self._base = f"http://{host}:{port}"
        self._headers = {API_KEY_HEADER: api_key} if api_key else {}

    async def _request(self, method: str, path: str, payload: Any = None) -> Any:
        try:
            async with asyncio.timeout(TIMEOUT):
                async with self._session.request(
                    method, f"{self._base}{path}", headers=self._headers, json=payload
                ) as resp:
                    if resp.status in (401, 403):
                        raise Rego6xxAuthError("Ogiltig API-nyckel")
                    resp.raise_for_status()
                    text = await resp.text()
            return json.loads(text) if text.strip() else None
        except (aiohttp.ClientError, TimeoutError) as err:
            raise Rego6xxConnectionError(f"{method} {path}: {err}") from err
        except ValueError as err:
            raise Rego6xxApiError(f"Ogiltigt JSON-svar från {path}") from err

    async def async_health(self) -> None:
        """GET /health (kräver ingen nyckel)."""
        await self._request("GET", "/health")

    async def async_info(self) -> dict[str, Any]:
        info = await self._request("GET", f"{API_PREFIX}/info")
        return info if isinstance(info, dict) else {}

    async def async_status(self) -> dict[str, dict[str, dict[str, Any]]]:
        return normalize_status(await self._request("GET", f"{API_PREFIX}/status"))

    async def async_set_setting(self, key: str, value: float) -> None:
        await self._request(
            "POST", f"{API_PREFIX}/settings/{quote(key, safe='')}", {"value": value}
        )

    async def async_press_key(self, key: str) -> None:
        await self._request("POST", f"{API_PREFIX}/keys/{quote(key, safe='')}")
