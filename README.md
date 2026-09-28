# Rego 6XX

Home Assistant-integration (HACS) för IVT/Bosch-värmepumpar med Rego 600-styrning.
Den pratar med **Rego600 REST API**-appen (FastAPI) som läser pumpen över serieporten.

## Installation

HACS → ⋮ → *Custom repositories* → `https://github.com/DewGew/rego6xx`, kategori **Integration** →
installera → starta om Home Assistant → *Inställningar → Enheter & tjänster → Lägg till integration → Rego 6XX*.

Ange **host**, **port** (standard 8600) och **API-nyckel** (samma som `REGO_API_KEY`, lämna tomt om den inte används).
Anslutningen valideras med `GET /health` och `GET /api/v1/info`.
Pollintervallet för `/api/v1/status` (standard 30 s, 15–300 s) ändras under *Konfigurera*.

## Entiteter

| Källa i `/api/v1/status` | Plattform | Detaljer |
|---|---|---|
| `sensors` | sensor | °C → `temperature`, `%` för tillsatsvärme; `state_class: measurement` |
| `power` | sensor | `power` (W), `measurement`. Ett värde per komponent + total |
| `energy_total_kwh` | sensor | *Total energy*, `energy` (kWh), **`total_increasing`** |
| `display` | sensor | Displayrader, diagnostik, **avstängda som standard** |
| `binary_sensors` | binary_sensor | `alarm` → problem, kompressor/pumpar → running |
| `leds` | binary_sensor | Diagnostik |
| `connected` | binary_sensor | *Serial connection* (connectivity). Övriga entiteter blir otillgängliga när den är av |
| `settings` | number | `min`/`max`/`step` från svaret, skrivs via `POST /api/v1/settings/{key}` |
| fasta | button | `1`, `2`, `3`, `wheel_left`, `wheel_right` via `POST /api/v1/keys/{key}` |

- `unique_id` = `{entry_id}_{slug}`. Sluggen är nyckeln i svaret, med prefix (`power_`, `energy_`, `display_`,
  `leds_`, `connection_`, `keys_`) för grupper som delar plattform.
- Alla entiteter delar en `DeviceInfo` byggd från `/api/v1/info` (modell, tillverkare, pumpstorlek, API-version).
- Efter varje POST körs `coordinator.async_request_refresh()`.
- Nya poster i `/status` blir nya entiteter utan omstart.

> **Obs:** `power` och `energy_total_kwh` är *uppskattningar* i API-appen (på/av × nominell effekt per
> pumpstorlek), inte mätvärden.
