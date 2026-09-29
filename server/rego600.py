"""Rego600 REST API + webbapp.

Läser en IVT/Bosch-värmepump med Rego 600-styrning över serieporten,
cachar värdena i bakgrunden och exponerar dem via ett REST-API som en
HACS-integration (DataUpdateCoordinator) kan polla.
"""
import json
import logging
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from typing import Callable, Optional

import serial
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

VERSION = "1.0.0"

# ----------------------------------------------------------------------------
# Konfiguration (miljövariabler)
# ----------------------------------------------------------------------------
SERIAL_PORT = os.getenv("REGO_SERIAL_PORT", "/dev/ttyUSB0")
BAUDRATE = int(os.getenv("REGO_BAUDRATE", "19200"))
PUMP_SIZE_KW = int(os.getenv("REGO_PUMP_SIZE_KW", "5"))
MODEL = os.getenv("REGO_MODEL", "IVT Greenline E5")
API_KEY = os.getenv("REGO_API_KEY", "")  # tom = ingen autentisering
ENERGY_FILE = os.getenv("REGO_ENERGY_FILE", "energy_total.json")
FAST_INTERVAL = float(os.getenv("REGO_POLL_INTERVAL", "15"))      # sensorer, pumpar, LED
SETTINGS_INTERVAL = float(os.getenv("REGO_SETTINGS_INTERVAL", "60"))
DISPLAY_INTERVAL = float(os.getenv("REGO_DISPLAY_INTERVAL", "2"))
LOG_LEVEL = os.getenv("REGO_LOG_LEVEL", "INFO")
DUMMY = os.getenv("REGO_DUMMY", "0").lower() in ("1", "true", "yes")  # simulerad värmepump

logging.basicConfig(level=LOG_LEVEL, format="[%(levelname)s] %(message)s")
log = logging.getLogger("rego600")

# ----------------------------------------------------------------------------
# Protokoll
# ----------------------------------------------------------------------------
PUMP_ADDRESS = 0x81
PC_ADDRESS = 0x01
READ_FRONT_PANEL = 0x00
WRITE_FRONT_PANEL = 0x01
READ_SYSTEM_REGISTER = 0x02
WRITE_SYSTEM_REGISTER = 0x03
READ_DISPLAY = 0x20


def slug(name: str) -> str:
    """'Radiator Return GT1' -> 'radiator_return_gt1', '+20° out' -> 'plus20_out'."""
    s = name.lower().replace("+", "plus").replace("-", "minus")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


# --- Temperatursensorer (värde/10 = °C) ---
SENSOR_MAP = {
    "Radiator Return GT1": 0x0209,
    "Radiator Target GT1": 0x006E,
    "Outdoor GT2": 0x020A,
    "Hot Water GT3": 0x020B,
    "Hot Water Target GT3": 0x002B,
    "Forward Target GT4": 0x006D,
    "Room GT5": 0x020D,
    "Compressor GT6": 0x020E,
    "Heat fluid out GT8": 0x020F,
    "Heat fluid in GT9": 0x0210,
    "Cold fluid in GT10": 0x0211,
    "Cold fluid out GT11": 0x0212,
    "GT3 On": 0x0073,
    "GT3 Off": 0x0074,
}

# --- Procentvärde (värde/10 = %) ---
PERCENT_MAP = {"Add Heat Percentage": 0x006C}

# --- På/av ---
BINARY_MAP = {
    "Three-way Valve": 0x0205,
    "Radiator Pump P1": 0x0203,
    "Heat carrier pump P2": 0x0204,
    "Ground loop pump P3": 0x01FD,
    "Compressor": 0x01FE,
    "Alarm": 0x0206,
}
# Tillsatsvärme: två steg, namn beror på pumpstorlek
if PUMP_SIZE_KW in (14, 16):
    ADD_HEAT_MAP = {"Add heat 5kw": 0x01FF, "Add heat 10kw": 0x0200}
else:
    ADD_HEAT_MAP = {"Add heat 3kw": 0x01FF, "Add heat 6kw": 0x0200}
BINARY_MAP.update(ADD_HEAT_MAP)

LED_MAP = {
    "LED1 Power On": 0x0012,
    "LED2 Pump": 0x0013,
    "LED3 Add Heat": 0x0014,
    "LED4 Boiler": 0x0015,
    "LED5 Alarm": 0x0016,
}

DISPLAY_ROWS = {"Row 1": 0x0000, "Row 2": 0x0001, "Row 3": 0x0002, "Row 4": 0x0003}

KEYS = {"1": 0x0009, "2": 0x000A, "3": 0x000B}
WHEEL_REG = 0x0044

# --- Inställningar: namn, register, min, max, steg (värden i °C, register = värde*10) ---
_CURVE_POINTS = [
    ("+20", 0x001E), ("+15", 0x001C), ("+10", 0x001A), ("+5", 0x0018),
    ("0", 0x0016), ("-5", 0x0014), ("-10", 0x0012), ("-15", 0x0010),
    ("-20", 0x000E), ("-25", 0x000C), ("-30", 0x000A), ("-35", 0x0008),
]
SETTINGS = {
    "Indoor temp setting": (0x0021, 10, 30, 0.1),
    "Heat curve": (0x0000, 0, 10, 0.1),
    "Heat curve fine adj.": (0x0001, -10, 10, 0.1),
    "Curve infl. by in-temp.": (0x0022, -10, 10, 0.1),
    "Heat curve coupling diff.": (0x0002, 0, 15, 1),
}
for _t, _reg in _CURVE_POINTS:
    SETTINGS[f"Adjust curve at {_t}° out"] = (_reg, -10, 10, 0.1)
SETTING_SLUGS = {slug(n): n for n in SETTINGS}

# --- Effekt (W) beroende på pumpstorlek ---
POWER = {
    "compressor": 1500, "add_heat_step1": 3000, "add_heat_step2": 6000,
    "pump_p1": 55, "pump_p2": 46, "pump_p3": 106,
}
_OVERRIDES = {
    4: {"compressor": 1100, "pump_p1": 0, "pump_p2": 35, "pump_p3": 70},
    7: {"compressor": 1850},
    9: {"compressor": 2500},
    11: {"compressor": 4600},
    14: {"compressor": 4100, "add_heat_step1": 5250, "add_heat_step2": 10500},
    16: {"compressor": 4600, "add_heat_step1": 5250, "add_heat_step2": 10500,
         "pump_p1": 90, "pump_p2": 165},
}
POWER.update(_OVERRIDES.get(PUMP_SIZE_KW, {}))


# ----------------------------------------------------------------------------
# Paketbygge / avkodning
# ----------------------------------------------------------------------------
def checksum(packet: list) -> int:
    c = 0
    for b in packet[2:8]:
        c ^= b
    return c


def encode_register(v: int) -> list:
    v &= 0xFFFF
    return [(v & 0xC000) >> 14, (v & 0x3F80) >> 7, v & 0x007F]


def build_request(command: int, register: int) -> bytes:
    pkt = [PUMP_ADDRESS, command] + encode_register(register) + [0, 0, 0]
    pkt.append(checksum(pkt))
    return bytes(pkt)


def build_write(command: int, register: int, value_bytes: list) -> bytes:
    pkt = [PUMP_ADDRESS, command] + encode_register(register) + value_bytes
    pkt.append(checksum(pkt))
    return bytes(pkt)


def decode_value(data: bytes) -> int:
    raw = (data[1] << 14) | (data[2] << 7) | data[3]
    return raw - 0x10000 if raw >= 0x8000 else raw  # 16-bit signed


def decode_display(data: bytes) -> str:
    if len(data) != 42 or data[0] != PC_ADDRESS:
        raise ValueError("Ogiltigt displaysvar")
    out = ""
    for i in range(1, 41, 2):
        ch = chr(((data[i] & 0x0F) << 4) | (data[i + 1] & 0x0F))
        out += {"ÿ": "", "ß": "°"}.get(ch, ch)
    return out.strip()


# ----------------------------------------------------------------------------
# Seriebuss
# ----------------------------------------------------------------------------
class RegoBus:
    def __init__(self):
        self.ser: Optional[serial.Serial] = None
        self.lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return self.ser is not None and self.ser.is_open

    def connect(self) -> bool:
        try:
            self.ser = serial.Serial(
                SERIAL_PORT, BAUDRATE, serial.EIGHTBITS, serial.PARITY_NONE,
                serial.STOPBITS_ONE, timeout=1,
            )
            time.sleep(1)
            log.info("Ansluten till %s", SERIAL_PORT)
            return True
        except Exception as e:
            log.error("Serieportsfel: %s", e)
            self.ser = None
            return False

    def close(self):
        try:
            if self.ser:
                self.ser.close()
        finally:
            self.ser = None

    def _read(self, command: int, reg: int, length: int,
              decode: Callable, delay: float = 0.05):
        if not self.connected:
            raise serial.SerialException("Inte ansluten")
        try:
            with self.lock:
                self.ser.reset_input_buffer()
                self.ser.write(build_request(command, reg))
                resp = self.ser.read(length)
                time.sleep(delay)
        except serial.SerialException:
            self.close()
            raise
        if len(resp) != length or resp[0] != PC_ADDRESS:
            log.debug("Ofullständigt svar för %s", hex(reg))
            return None
        if length == 5 and (resp[1] ^ resp[2] ^ resp[3]) != resp[4]:
            log.debug("Checksummefel för %s", hex(reg))
            return None
        try:
            return decode(resp)
        except ValueError:
            return None

    def read_system(self, reg: int):
        return self._read(READ_SYSTEM_REGISTER, reg, 5, decode_value)

    def read_front_panel(self, reg: int):
        return self._read(READ_FRONT_PANEL, reg, 5, decode_value)

    def read_display(self, row: int):
        return self._read(READ_DISPLAY, row, 42, decode_display)

    def _write(self, packet: bytes) -> bool:
        if not self.connected:
            raise serial.SerialException("Inte ansluten")
        try:
            with self.lock:
                self.ser.reset_input_buffer()
                self.ser.write(packet)
                time.sleep(0.1)
                resp = self.ser.read(1)
        except serial.SerialException:
            self.close()
            raise
        return len(resp) == 1 and resp[0] == PC_ADDRESS

    def write_setting(self, reg: int, raw: int) -> bool:
        return self._write(build_write(WRITE_SYSTEM_REGISTER, reg, encode_register(raw)))

    def press_key(self, reg: int) -> bool:
        return self._write(build_write(WRITE_FRONT_PANEL, reg, encode_register(1)))

    def turn_wheel(self, direction: str) -> bool:
        value = 0x1FFFFF if direction == "left" else 0x000001
        vb = [(value & 0xC0000) >> 18, (value & 0x3F800) >> 11, value & 0x7F]
        return self._write(build_write(WRITE_FRONT_PANEL, WHEEL_REG, vb))


# ----------------------------------------------------------------------------
# Dummy-värmepump (REGO_DUMMY=1) – simulerar en pump utan hårdvara
# ----------------------------------------------------------------------------
class DummyBus(RegoBus):
    """Samma gränssnitt som RegoBus, men värdena simuleras.

    Utetemp varierar sinusformat (period 10 min), kompressorn cyklar,
    tillsatsvärme går in korta perioder och varmvattenladdning sker
    regelbundet. Inställningar kan skrivas och behålls i minnet.
    """

    def __init__(self):
        super().__init__()
        self.t0 = time.time()
        self.settings_raw = {reg: 0 for reg, *_ in SETTINGS.values()}
        self.settings_raw[SETTINGS["Indoor temp setting"][0]] = 210
        self.settings_raw[SETTINGS["Heat curve"][0]] = 50
        self.settings_raw[SETTINGS["Heat curve coupling diff."][0]] = 100
        self.last_key = "-"

    @property
    def connected(self) -> bool:
        return True

    def connect(self) -> bool:
        return True

    def close(self):
        pass

    def _model(self) -> dict:
        """Returnerar {register: råvärde} för nuvarande tidpunkt."""
        import math
        t = time.time() - self.t0
        indoor = self.settings_raw[SETTINGS["Indoor temp setting"][0]] / 10
        curve = self.settings_raw[SETTINGS["Heat curve"][0]] / 10

        outdoor = 2 + 8 * math.sin(2 * math.pi * t / 600)
        comp = (t % 240) < 150
        hot_water = (t % 480) > 400
        add1 = outdoor < -3 or (t % 600) < 45
        add2 = outdoor < -6
        target = 20 + curve * (20 - outdoor) * 0.35
        wob = math.sin(t / 7) * 0.4

        v = {
            "Radiator Target GT1": target,
            "Radiator Return GT1": target - 5 + wob + (2 if comp else -2),
            "Outdoor GT2": outdoor,
            "Hot Water GT3": 49 + 4 * math.sin(2 * math.pi * t / 480),
            "Hot Water Target GT3": 50,
            "Forward Target GT4": target,
            "Room GT5": indoor - 0.3 + wob / 4,
            "Compressor GT6": 62 + wob * 3 if comp else 28,
            "Heat fluid out GT8": target + 2 + wob if comp else target - 3,
            "Heat fluid in GT9": target - 3 + wob if comp else target - 5,
            "Cold fluid in GT10": 3 + wob if comp else 5,
            "Cold fluid out GT11": -1 + wob if comp else 4,
            "GT3 On": 45,
            "GT3 Off": 52,
        }
        raw = {SENSOR_MAP[n]: round(x * 10) for n, x in v.items()}

        step_regs = list(ADD_HEAT_MAP.values())
        raw.update({
            PERCENT_MAP["Add Heat Percentage"]: 500 if add1 and not add2 else (1000 if add2 else 0),
            BINARY_MAP["Three-way Valve"]: int(hot_water),
            BINARY_MAP["Radiator Pump P1"]: int(comp and not hot_water),
            BINARY_MAP["Heat carrier pump P2"]: int(comp),
            BINARY_MAP["Ground loop pump P3"]: int(comp),
            BINARY_MAP["Compressor"]: int(comp),
            BINARY_MAP["Alarm"]: 0,
            step_regs[0]: int(add1),
            step_regs[1]: int(add2),
            LED_MAP["LED1 Power On"]: 1,
            LED_MAP["LED2 Pump"]: int(comp),
            LED_MAP["LED3 Add Heat"]: int(add1 or add2),
            LED_MAP["LED4 Boiler"]: 0,
            LED_MAP["LED5 Alarm"]: 0,
        })
        raw.update(self.settings_raw)
        return raw

    def read_system(self, reg: int):
        return self._model().get(reg)

    def read_front_panel(self, reg: int):
        return self._model().get(reg)

    def read_display(self, row: int):
        m = self._model()
        out = m[SENSOR_MAP["Outdoor GT2"]] / 10
        room = m[SENSOR_MAP["Room GT5"]] / 10
        rows = [
            f"Rego600 K1(DUMMY)",
            f"Ute: {out:5.1f}°  Rum: {room:4.1f}°",
            f"260915 23:30:20 Ti",
            f"Värme Info meny",
        ]
        return rows[row]

    def write_setting(self, reg: int, raw: int) -> bool:
        self.settings_raw[reg] = raw
        return True

    def press_key(self, reg: int) -> bool:
        self.last_key = {v: k for k, v in KEYS.items()}.get(reg, "?")
        return True

    def turn_wheel(self, direction: str) -> bool:
        self.last_key = f"wheel {direction}"
        return True


# ----------------------------------------------------------------------------
# Tillstånd + bakgrundspollning
# ----------------------------------------------------------------------------
class Poller:
    def __init__(self, bus: RegoBus):
        self.bus = bus
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.state = {
            "sensors": {}, "binary_sensors": {}, "leds": {},
            "settings": {}, "display": {}, "power": {}, "last_update": None,
        }
        self.energy_kwh = self._load_energy()
        self._last_energy_ts = time.time()
        self._last_energy_save = time.time()

    # --- energilagring ---
    @staticmethod
    def _load_energy() -> float:
        try:
            with open(ENERGY_FILE) as f:
                return float(json.load(f).get("energy_total_kwh", 0.0))
        except Exception:
            return 0.0

    def save_energy(self):
        try:
            with open(ENERGY_FILE, "w") as f:
                json.dump({"energy_total_kwh": round(self.energy_kwh, 3)}, f)
        except Exception as e:
            log.warning("Kunde inte spara energi: %s", e)

    # --- poll-grupper ---
    def _poll_fast(self):
        bus, st = self.bus, {}
        sensors, binary, leds = {}, {}, {}

        for name, reg in SENSOR_MAP.items():
            v = bus.read_system(reg)
            if v is not None:
                sensors[slug(name)] = {"name": name, "value": round(v / 10, 1), "unit": "°C"}
        for name, reg in PERCENT_MAP.items():
            v = bus.read_system(reg)
            if v is not None:
                sensors[slug(name)] = {"name": name, "value": round(v / 10, 1), "unit": "%"}
        for name, reg in BINARY_MAP.items():
            v = bus.read_system(reg)
            if v is not None:
                binary[slug(name)] = {"name": name, "state": v > 0, "raw": v}
        for name, reg in LED_MAP.items():
            v = bus.read_front_panel(reg)
            if v is not None:
                leds[slug(name)] = {"name": name, "state": v > 0}

        with self.lock:
            self.state["sensors"].update(sensors)
            self.state["binary_sensors"].update(binary)
            self.state["leds"].update(leds)
            self._update_power_locked()
            self.state["last_update"] = time.time()

    def _is_on(self, name: str) -> bool:
        return self.state["binary_sensors"].get(slug(name), {}).get("state", False)

    def _update_power_locked(self):
        step_names = list(ADD_HEAT_MAP)
        p = {
            "compressor": POWER["compressor"] if self._is_on("Compressor") else 0,
            "pump_p1": POWER["pump_p1"] if self._is_on("Radiator Pump P1") else 0,
            "pump_p2": POWER["pump_p2"] if self._is_on("Heat carrier pump P2") else 0,
            "pump_p3": POWER["pump_p3"] if self._is_on("Ground loop pump P3") else 0,
            "add_heat_step1": POWER["add_heat_step1"] if self._is_on(step_names[0]) else 0,
            "add_heat_step2": POWER["add_heat_step2"] if self._is_on(step_names[1]) else 0,
        }
        p["total"] = sum(p.values())
        self.state["power"] = p

        now = time.time()
        dt_h = min(now - self._last_energy_ts, 300) / 3600.0
        self.energy_kwh += p["total"] * dt_h / 1000.0
        self._last_energy_ts = now
        if now - self._last_energy_save >= 600:
            self.save_energy()
            self._last_energy_save = now

    def _poll_settings(self):
        out = {}
        for name, (reg, mn, mx, step) in SETTINGS.items():
            v = self.bus.read_system(reg)
            if v is not None:
                out[slug(name)] = {"name": name, "value": round(v / 10, 1),
                                   "min": mn, "max": mx, "step": step, "unit": "°C"}
        with self.lock:
            self.state["settings"].update(out)

    def _poll_display(self):
        out = {}
        for name, row in DISPLAY_ROWS.items():
            v = self.bus.read_display(row)
            if v is not None:
                out[slug(name)] = v
        with self.lock:
            self.state["display"].update(out)

    def run(self):
        due = {"fast": 0.0, "settings": 0.0, "display": 0.0}
        while not self.stop.is_set():
            if not self.bus.connected:
                if not self.bus.connect():
                    self.stop.wait(5)
                    continue
            now = time.time()
            try:
                if now >= due["fast"]:
                    self._poll_fast()
                    due["fast"] = now + FAST_INTERVAL
                if now >= due["settings"]:
                    self._poll_settings()
                    due["settings"] = now + SETTINGS_INTERVAL
                if now >= due["display"]:
                    self._poll_display()
                    due["display"] = now + DISPLAY_INTERVAL
            except serial.SerialException as e:
                log.error("Serialfel, försöker återansluta: %s", e)
            except Exception as e:
                log.warning("Pollningsfel: %s", e)
            self.stop.wait(0.1)

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def shutdown(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=5)
        self.save_energy()
        self.bus.close()

    def snapshot(self) -> dict:
        with self.lock:
            s = json.loads(json.dumps(self.state))
        s["energy_total_kwh"] = round(self.energy_kwh, 3)
        s["connected"] = self.bus.connected
        return s


bus = DummyBus() if DUMMY else RegoBus()
poller = Poller(bus)


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info("Startar Rego600 API %s (%s, %d kW)%s", VERSION, MODEL, PUMP_SIZE_KW,
             " – DUMMY-läge (simulerad pump)" if DUMMY else "")
    poller.start()
    yield
    poller.shutdown()


app = FastAPI(title="Rego600 API", version=VERSION, lifespan=lifespan)


# ----------------------------------------------------------------------------
# Autentisering
# ----------------------------------------------------------------------------
def require_key(x_api_key: str = Header(default=""), api_key: str = Query(default="")):
    if API_KEY and API_KEY not in (x_api_key, api_key):
        raise HTTPException(401, "Ogiltig API-nyckel")


auth = [Depends(require_key)]


# ----------------------------------------------------------------------------
# API
# ----------------------------------------------------------------------------
class SettingValue(BaseModel):
    value: float


@app.get("/health")
def health():
    return {"status": "ok", "connected": bus.connected, "version": VERSION, "dummy": DUMMY}


@app.get("/api/v1/info", dependencies=auth)
def info():
    return {
        "version": VERSION, "model": MODEL, "pump_size_kw": PUMP_SIZE_KW,
        "manufacturer": "IVT/Bosch", "serial_port": SERIAL_PORT,
        "connected": bus.connected, "dummy": DUMMY,
        "add_heat_steps": [
            {"key": slug(n), "name": n, "power_w": POWER[f"add_heat_step{i + 1}"]}
            for i, n in enumerate(ADD_HEAT_MAP)
        ],
        "power_w": POWER,
    }


@app.get("/api/v1/status", dependencies=auth)
def status():
    """Allt i ett anrop – tänkt för DataUpdateCoordinator."""
    return poller.snapshot()


@app.get("/api/v1/sensors", dependencies=auth)
def sensors():
    return poller.snapshot()["sensors"]


@app.get("/api/v1/binary_sensors", dependencies=auth)
def binary_sensors():
    return poller.snapshot()["binary_sensors"]


@app.get("/api/v1/leds", dependencies=auth)
def leds():
    return poller.snapshot()["leds"]


@app.get("/api/v1/display", dependencies=auth)
def display():
    return poller.snapshot()["display"]


@app.get("/api/v1/power", dependencies=auth)
def power():
    s = poller.snapshot()
    return {"power_w": s["power"], "energy_total_kwh": s["energy_total_kwh"]}


@app.get("/api/v1/settings", dependencies=auth)
def settings():
    return poller.snapshot()["settings"]


@app.post("/api/v1/settings/{key}", dependencies=auth)
def set_setting(key: str, body: SettingValue):
    """Sätt en inställning. Värdet anges i °C (t.ex. 21.5)."""
    name = SETTING_SLUGS.get(key)
    if not name:
        raise HTTPException(404, f"Okänd inställning: {key}")
    reg, mn, mx, _ = SETTINGS[name]
    if not mn <= body.value <= mx:
        raise HTTPException(422, f"Värdet måste vara mellan {mn} och {mx}")
    try:
        ok = bus.write_setting(reg, round(body.value * 10))
    except serial.SerialException as e:
        raise HTTPException(503, f"Serialfel: {e}")
    if not ok:
        raise HTTPException(502, "Ingen kvittens från värmepumpen")
    with poller.lock:  # optimistisk uppdatering av cachen
        if key in poller.state["settings"]:
            poller.state["settings"][key]["value"] = round(body.value, 1)
    log.info("Inställning %s -> %s", name, body.value)
    return {"key": key, "value": body.value, "ok": True}


@app.post("/api/v1/keys/{key}", dependencies=auth)
def press(key: str):
    """key: 1, 2, 3, wheel_left eller wheel_right."""
    try:
        if key in KEYS:
            ok = bus.press_key(KEYS[key])
        elif key in ("wheel_left", "wheel_right"):
            ok = bus.turn_wheel(key.split("_")[1])
        else:
            raise HTTPException(404, f"Okänd knapp: {key}")
    except serial.SerialException as e:
        raise HTTPException(503, f"Serialfel: {e}")
    if not ok:
        raise HTTPException(502, "Ingen kvittens från värmepumpen")
    return {"key": key, "ok": True}


# ----------------------------------------------------------------------------
# Enkel webbapp
# ----------------------------------------------------------------------------
DASHBOARD = """<!doctype html><html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Rego600</title>
<style>
:root{--bg:#f5f6f8;--card:#fff;--fg:#1c2330;--mut:#6b7686;--acc:#0a7cff;--on:#1a9d55}
@media(prefers-color-scheme:dark){:root{--bg:#12161d;--card:#1b212b;--fg:#e6e9ef;--mut:#8a94a6}}
body{margin:0;font-family:system-ui,sans-serif;background:var(--bg);color:var(--fg);padding:16px}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--mut);font-size:13px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-bottom:16px}
.c{background:var(--card);border-radius:10px;padding:10px 12px}.c b{display:block;font-size:20px}
.c span{font-size:12px;color:var(--mut)}.on b{color:var(--on)}
pre{background:#0b0f14;color:#9fe3b1;padding:10px;border-radius:8px;overflow:auto}
h2{font-size:14px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em}
input{width:70px}button{margin-left:6px;background:var(--acc);color:#fff;border:0;border-radius:6px;padding:4px 10px}
</style></head><body>
<h1>Rego600</h1><div class="sub" id="sub">Laddar…</div>
<h2>Display</h2><pre id="disp"></pre>
<h2>Temperaturer</h2><div class="grid" id="sens"></div>
<h2>Status</h2><div class="grid" id="bin"></div>
<h2>Effekt</h2><div class="grid" id="pow"></div>
<h2>Inställningar</h2><div class="grid" id="set"></div>
<script>
const K=new URLSearchParams(location.search).get('api_key')||'';
const H=K?{'X-API-Key':K}:{};
const card=(l,v,c='')=>`<div class="c ${c}"><span>${l}</span><b>${v}</b></div>`;
async function load(){
 try{
  const s=await (await fetch('api/v1/status',{headers:H})).json();
  document.getElementById('sub').textContent=(s.connected?'Ansluten':'Ej ansluten')+' · '+new Date().toLocaleTimeString();
  disp.textContent=Object.values(s.display).join('\\n');
  sens.innerHTML=Object.values(s.sensors).map(x=>card(x.name,x.value+' '+x.unit)).join('');
  bin.innerHTML=Object.values(s.binary_sensors).map(x=>card(x.name,x.state?'PÅ':'AV',x.state?'on':'')).join('');
  pow.innerHTML=Object.entries(s.power).map(([k,v])=>card(k,v+' W')).join('')+card('Total energi',s.energy_total_kwh+' kWh');
  if(!document.activeElement||document.activeElement.tagName!=='INPUT')
   set.innerHTML=Object.entries(s.settings).map(([k,x])=>`<div class="c"><span>${x.name}</span>
   <input id="i_${k}" type="number" step="${x.step}" min="${x.min}" max="${x.max}" value="${x.value}">
   <button onclick="save('${k}')">OK</button></div>`).join('');
 }catch(e){sub.textContent='Fel: '+e}
}
async function save(k){
 const v=parseFloat(document.getElementById('i_'+k).value);
 const r=await fetch('api/v1/settings/'+k,{method:'POST',headers:{...H,'Content-Type':'application/json'},body:JSON.stringify({value:v})});
 alert(r.ok?'Sparat':'Fel: '+(await r.text()));load();
}
load();setInterval(load,5000);
</script></body></html>"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index():
    return DASHBOARD


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv("REGO_HOST", "0.0.0.0"), port=int(os.getenv("REGO_PORT", "8600")))
