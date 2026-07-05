# Intel RAPL Power Monitor

A minimal, high-performance, and visually stunning real-time CPU and DRAM power monitoring dashboard built with **FastAPI** (Python 3.11+) and **Chart.js**.

This project provides a lightweight daemon and web API that polls the Linux Intel RAPL (Running Average Power Limit) powercap interface every second, calculates instantaneous power consumption via energy delta calculations, and displays telemetry on a beautiful glassmorphic dark-mode dashboard.

## 🛠 Features

- **Real-Time Polling:** Reads Intel RAPL energy counters every `1.0s` and computes power (`Watts`) from the microjoule (`energy_uj`) deltas.
- **Robust Fallback Engine:** Automatically detects if `/sys/class/powercap/intel-rapl` files are missing or restrictively locked (standard on modern Linux distros due to side-channel concerns). Automatically falls back to a realistic simulated telemetry engine so the system remains fully functional and visual without administrative root privileges.
- **Enterprise REST API:** Exposes clean JSON endpoints for current telemetry, cumulative statistical summaries, and health statuses.
- **Rich Dashboard:** A premium dark-theme interface with smooth micro-animations, real-time Chart.js line graphs (with area gradient fills), peak indicators, and statistics grids.
- **Full Test Suite:** Fully covered endpoints and logic via `pytest`.

---

## 📂 Project Structure

```text
intel-rapl-power-monitor/
├── power_monitor/
│   ├── __init__.py
│   ├── app.py              # Main FastAPI application & background reader loop
│   └── static/
│       └── dashboard.html  # Premium frontend dashboard served by the server
├── tests/
│   └── test_power_monitor.py # pytest coverage for APIs and math logic
├── README.md               # Setup, documentation, and usage guide
└── requirements.txt        # Python dependency manifest
```

---

## ⚡ Quick Start

### 1. Set Up Virtual Environment

To isolate dependencies, set up a Python virtual environment:

```bash
# Navigate to project directory
cd /home/veno/Projects/intel-rapl-power-monitor

# Create a virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate
```

### 2. Install Dependencies

Install the required Python modules:

```bash
pip install -r requirements.txt
```

*(If `pip` is not available globally, the environment creation steps below will automatically bootstrap pip inside the `.venv`).*

### 3. Run the FastAPI Server

Start the application with Uvicorn:

```bash
uvicorn power_monitor.app:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser and navigate to:
👉 **[http://localhost:8000](http://localhost:8000)**

---

## ▶️ Run / Verification Command

Single-shot run command for port 8000 using the venv Python from this repo:

```bash
/home/veno/Projects/intel-rapl-power-monitor/.venv/.venv/bin/python3 -m uvicorn power_monitor.app:app --host 0.0.0.0 --port 8000
```

Quick verifications after starting:

```bash
curl -f http://127.0.0.1:8000/healthz
curl -f http://127.0.0.1:8000/api/power | jq
curl -f http://127.0.0.1:8000/api/summary | jq '{uptime, history_len:(.history|length), pkg_wh:.package.total_energy_wh, dram_wh:.dram.total_energy_wh}'
```

Note: if RAPL sysfs returns permission errors, the server falls back to realistic simulated telemetry automatically. To allow direct hardware reading without sudo for the user running the server:

```bash
sudo chmod -R a+r /sys/class/powercap/intel-rapl:0 /sys/class/powercap/intel-rapl:0:2
```

If you prefer to keep it running as a service, see `scripts/systemd/intel-rapl-power-monitor.service`.

---

## 📊 API Reference

| Endpoint | Method | Description | Example Response |
|---|---|---|---|
| `/` | `GET` | Serves the HTML5 Dashboard interface | `HTML content` |
| `/healthz` | `GET` | Health status and RAPL access check | `{"status": "ok", "sysfs_accessible": false, "modes": {"package": "mock", "dram": "mock"}}` |
| `/api/power` | `GET` | Latest instantaneous power reading (W) | `{"timestamp": "2026-07-05T13:52:01Z", "package": {"power_w": 34.2, "is_mock": true}, ...}` |
| `/api/summary` | `GET` | Historic metrics, averages, min/max & total energy | See below |

### `/api/summary` Payload Example

```json
{
  "uptime_seconds": 120,
  "package": {
    "average_power_w": 34.821,
    "max_power_w": 42.15,
    "min_power_w": 28.51,
    "total_energy_joules": 4178.52,
    "total_energy_wh": 1.1607,
    "is_mock": true
  },
  "dram": {
    "average_power_w": 6.124,
    "max_power_w": 7.82,
    "min_power_w": 4.98,
    "total_energy_joules": 734.88,
    "total_energy_wh": 0.204133,
    "is_mock": true
  },
  "history": [
    {
      "timestamp": "2026-07-05T13:52:00Z",
      "epoch": 1783259520.0,
      "package_w": 34.5,
      "dram_w": 6.1
    }
  ]
}
```

---

## 🧪 Testing

The project includes unit and integration tests written using `pytest` and `fastapi.testclient`.

To run the test suite, run:

```bash
pytest -v
```

---

## ⚙️ Intel RAPL Reference

Linux exports energy readings via `sysfs` powercap interface:
- **CPU Package-0:** `/sys/class/powercap/intel-rapl:0/energy_uj`
- **DRAM (Memory):** `/sys/class/powercap/intel-rapl:0:2/energy_uj`

### Permission Setup (For live sysfs readings)
On standard configurations, these files are readable only by `root` or users with `CAP_SYS_RAWIO` permissions. To run the app with live hardware reading without root, you can change permissions (requires sudo):
```bash
sudo chmod -R a+r /sys/class/powercap/intel-rapl:0
```
Without this, the app will gracefully report `"is_mock": true` and generate realistic simulated telemetry.
