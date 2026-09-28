"""Asynkron HTTP-klient för Rego 6XX (inga Home Assistant-beroenden)."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import quote

import aiohttp

TIMEOUT = 10
API_KEY_HEADER = "X-API-Key"

# Grupper i /status-svaret
GROUPS = (
    "sensors",
    "power",
    "energy",
    "binary_sensors",
    "leds",
    "settings",
    "keys",
)


class Rego6xxApiError(Exception):
    """Grundfel."""


class Rego6xxConnectionError(Rego6xxApiError):
    """Kunde inte nå enheten."""


class Rego6xxAuthError(Rego6xxApiError):
    """Ogiltig API-nyckel."""


def normalize_group(data: Any) -> dict[str, dict[str, Any]]:
    """Gör om en grupp till {slug: {name, value, ...}}.

    Accepterar dict av dict, dict av skalärer, lista av dict eller lista av str.
    """
    result: dict[str, dict[str, Any]] = {}
    if isinstance(data, dict):
        for key, item in data.items():
            result[str(key)] = dict(item) if isinstance(item, dict) else {"value": item}
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                key = item.get("slug") or item.get("key") or item.get("id") or item.get("name")
                if key is not None:
                    result[str(key)] = dict(item)
            elif item is not None:
                result[str(item)] = {"name": str(item)}
    return result


def normalize_status(raw: Any) -> dict[str, dict[str, dict[str, Any]]]:
    if not isinstance(raw, dict):
        raise Rego6xxApiError("Oväntat svar från /status")
    return {group: normalize_group(raw.get(group)) for group in GROUPS}


class Rego6xxApi:
    """Klient mot Rego 6XX-brygga."""

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
        await self._request("GET", "/health")

    async def async_info(self) -> dict[str, Any]:
        info = await self._request("GET", "/info")
        return info if isinstance(info, dict) else {}

    async def async_status(self) -> dict[str, dict[str, dict[str, Any]]]:
        return normalize_status(await self._request("GET", "/status"))

    async def async_set_setting(self, key: str, value: float | int) -> None:
        await self._request("POST", f"/settings/{quote(key, safe='')}", {"value": value})

    async def async_press_key(self, key: str) -> None:
        await self._request("POST", f"/keys/{quote(key, safe='')}")
