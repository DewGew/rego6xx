# Rego600 API Server

A FastAPI-based server that communicates with an IVT/Bosch heat pump running Rego 600 over a serial connection.

The server polls the heat pump in the background, caches the latest values, and exposes them through a REST API. The **Rego 6XX** Home Assistant integration (located in the repository root) uses this API to retrieve data from the heat pump.

## Running with Docker Compose

```bash
cd server
cp .env.example .env   # Adjust as needed
docker compose up -d --build
```

Once the container is running:

- Open `http://<server>:8600/` for a simple web dashboard.
- Open `http://<server>:8600/docs` for the interactive API documentation (Swagger UI).

### Running without physical hardware

To test the server and Home Assistant integration without a real heat pump, set:

```env
REGO_DUMMY=1
```

Also remove the `devices:` entry from `docker-compose.yml`.

In dummy mode, the server uses a simulated heat pump, so no serial hardware is required.

## Running Directly with Python

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

REGO_SERIAL_PORT=/dev/ttyUSB0 REGO_API_KEY=secret python rego600.py
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `REGO_SERIAL_PORT` | `/dev/ttyUSB0` | Serial port connected to the heat pump |
| `REGO_BAUDRATE` | `19200` | Serial communication baud rate |
| `REGO_PUMP_SIZE_KW` | `5` | Heat pump output rating. Controls which auxiliary heater stages are exposed. 14/16 kW models use different stages |
| `REGO_MODEL` | `IVT Greenline E5` | Free-form model name, exposed through `/api/v1/info` |
| `REGO_API_KEY` | *(empty)* | API authentication key. Leave empty to disable authentication. The same key must be configured in the Home Assistant integration |
| `REGO_ENERGY_FILE` | `energy_total.json` | File used to persist accumulated energy data. Updated every 10 minutes |
| `REGO_POLL_INTERVAL` | `15` | Interval, in seconds, for polling sensors, binary sensors, and LEDs |
| `REGO_SETTINGS_INTERVAL` | `60` | Interval, in seconds, for polling settings |
| `REGO_DISPLAY_INTERVAL` | `2` | Interval, in seconds, for reading display lines |
| `REGO_LOG_LEVEL` | `INFO` | Logging level |
| `REGO_DUMMY` | `0` | Set to `1` to use a simulated heat pump instead of real hardware |
| `REGO_HOST` / `REGO_PORT` | `0.0.0.0` / `8600` | Host and port used when running `rego600.py` directly. When using Docker, the port is configured through `ports:` in `docker-compose.yml` |

## API Endpoints

The main endpoints are:

- `GET /health` — Health check; does not require authentication
- `GET /api/v1/info` — Server and heat pump information
- `GET /api/v1/status` — Returns all available data in a single response; this is the endpoint polled by the Home Assistant integration
- `GET /api/v1/sensors` — Sensor values
- `GET /api/v1/binary_sensors` — Binary sensor values
- `GET /api/v1/leds` — LED states
- `GET /api/v1/display` — Heat pump display data
- `GET /api/v1/power` — Power-related data
- `GET /api/v1/settings` — Current settings
- `POST /api/v1/settings/{key}` — Update a setting
- `POST /api/v1/keys/{key}` — Simulate a key press (`1`, `2`, `3`, `wheel_left`, `wheel_right`)

For the complete and always up-to-date API reference, visit:

`http://<server>:8600/docs`

## Hardware Requirements

The server requires a serial RS-232 connection to the heat pump's Rego 600 controller board, typically using a USB-to-serial adapter.

**Only one process can access the serial port at a time.** Do not run multiple instances of the server against the same serial device (for example, `/dev/ttyUSB0`).

If another application is already using the serial port, the Rego600 API server will not be able to communicate with the heat pump.
