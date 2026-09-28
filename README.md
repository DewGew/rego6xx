# Rego 6XX

Home Assistant integration (HACS) for Rego 6XX via an HTTP bridge.

## Installation

HACS → ⋮ → *Custom repositories* → `https://github.com/DewGew/rego6xx`, category **Integration** →
install → restart Home Assistant → *Settings → Devices & services → Add integration → Rego 6XX*.

You enter the **host**, **port**, and **API key**. The connection is validated using `GET /health` and `GET /info`.
The `/status` polling interval (default 30 s, 15–300 s) can be changed under the integration's *Configure* options.

## Expected API

The API key is sent in the `X-API-Key` header (change this in `api.py`).

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/health` | Returns 200 if the bridge is alive |
| GET  | `/info` | Device information → `DeviceInfo` |
| GET  | `/status` | All data, polled every 15–30 s |
| POST | `/settings/{key}` | Body `{"value": 42}` |
| POST | `/keys/{key}` | Presses a button |

`/info`:
```json
{"name": "Rego 6XX", "manufacturer": "Regin", "model": "Rego 637", "sw_version": "1.2.3", "serial": "ABC123"}
```

`/status` (each group can be either a dict or a list; scalar values are accepted as `value`):
```json
{
  "sensors":        {"gt1": {"name": "Radiator return", "value": 35.2, "unit": "°C", "device_class": "temperature"}},
  "power":          {"compressor": {"name": "Compressor power", "value": 1200}},
  "energy":         {"total": {"name": "Energy", "value": 1234.5}},
  "binary_sensors": {"compressor": {"name": "Compressor", "value": true}},
  "leds":           {"alarm": {"name": "Alarm LED", "value": false}},
  "settings":       {"heat_curve": {"name": "Heat curve", "value": 30, "min": 0, "max": 100, "step": 1, "unit": "°C"}},
  "keys":           {"up": {"name": "Up"}, "ok": {"name": "OK"}}
}
```

## Entities

| Group | Platform | Details |
|-------|----------|---------|
| `sensors` | sensor | `state_class: measurement` if the value is numeric |
| `power` | sensor | `device_class: power`, `measurement`, default unit W |
| `energy` | sensor | `device_class: energy`, **`total_increasing`**, default unit kWh |
| `binary_sensors` | binary_sensor | |
| `leds` | binary_sensor | category *diagnostic* |
| `settings` | number | `min`/`max`/`step` are included in the response; writes via POST |
| `keys` | button | POST on press |

- `unique_id` = `{entry_id}_{slug}`. The slug is the key in the response, but `power_`, `energy_`, and `leds_` are prefixed
  to avoid collisions with other groups on the same platform.
- All entities share a `DeviceInfo` built from `/info`.
- After every POST, `coordinator.async_request_refresh()` is called.
- New keys in `/status` become new entities without requiring a restart.
