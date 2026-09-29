FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rego600.py .

ENV REGO_HOST=0.0.0.0 \
    REGO_PORT=8600 \
    REGO_SERIAL_PORT=/dev/ttyUSB0 \
    REGO_BAUDRATE=19200 \
    REGO_PUMP_SIZE_KW=5 \
    REGO_MODEL="IVT Greenline E5" \
    REGO_API_KEY="" \
    REGO_ENERGY_FILE=/data/energy_total.json \
    REGO_POLL_INTERVAL=15 \
    REGO_SETTINGS_INTERVAL=60 \
    REGO_DISPLAY_INTERVAL=2 \
    REGO_LOG_LEVEL=INFO \
    REGO_DUMMY=0

VOLUME ["/data"]
EXPOSE 8600

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"REGO_PORT\"]}/health', timeout=3)" || exit 1

CMD ["python", "rego600.py"]
