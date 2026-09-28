"""Konstanter för Rego 6XX."""

DOMAIN = "rego6xx"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_PORT = 8600  # REGO_PORT i Rego600 API-appen
DEFAULT_SCAN_INTERVAL = 30  # sekunder
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 300

# Namn för nycklarna i /status -> power (värdena är W)
POWER_NAMES = {
    "compressor": "Compressor power",
    "pump_p1": "Radiator pump P1 power",
    "pump_p2": "Heat carrier pump P2 power",
    "pump_p3": "Ground loop pump P3 power",
    "add_heat_step1": "Add heat step 1 power",
    "add_heat_step2": "Add heat step 2 power",
    "total": "Total power",
}
