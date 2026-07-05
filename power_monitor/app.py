import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("power_monitor")

# Paths for Intel RAPL
RAPL_PATH_PKG = "/sys/class/powercap/intel-rapl:0"
RAPL_PATH_DRAM = "/sys/class/powercap/intel-rapl:0:2"

class RAPLReader:
    """
    Reads energy readings from Intel RAPL sysfs files and calculates power consumption.
    Includes an automatic fallback to simulation if files are missing or unreadable due to permissions.
    """
    def __init__(self, path: str, default_name: str, simulated_base_power: float):
        self.path = path
        self.default_name = default_name
        self.simulated_base_power = simulated_base_power
        
        self.energy_path = os.path.join(path, "energy_uj")
        self.max_range_path = os.path.join(path, "max_energy_range_uj")
        self.name_path = os.path.join(path, "name")
        
        self.name = self._read_name()
        self.max_energy_range = self._read_max_range()
        
        self.is_mock = False
        self.last_energy = None
        self.last_time = None
        
        # For simulation mode
        self.sim_energy = 100_000_000.0  # Starting energy in microjoules
        
    def _read_name(self) -> str:
        try:
            if os.path.exists(self.name_path):
                with open(self.name_path, "r") as f:
                    return f.read().strip()
        except Exception:
            pass
        return self.default_name

    def _read_max_range(self) -> int:
        try:
            if os.path.exists(self.max_range_path):
                with open(self.max_range_path, "r") as f:
                    return int(f.read().strip())
        except Exception:
            pass
        return 262143328850  # Default fallback max range from standard Intel RAPL (microjoules)

    def read_energy_uj(self) -> float:
        if self.is_mock:
            return self._simulated_read()
            
        try:
            with open(self.energy_path, "r") as f:
                return float(f.read().strip())
        except (PermissionError, FileNotFoundError, OSError) as e:
            # Log warning once when fallback occurs
            if not self.is_mock:
                logger.warning(
                    f"Unable to read RAPL energy from {self.energy_path} ({e}). "
                    f"Falling back to simulated data for {self.name}."
                )
            self.is_mock = True
            return self._simulated_read()

    def _simulated_read(self) -> float:
        now = time.time()
        if self.last_time is not None:
            dt = now - self.last_time
            # Introduce realistic fluctuations to the power
            import random
            fluctuation = random.uniform(-0.15, 0.15) * self.simulated_base_power
            current_sim_power = self.simulated_base_power + fluctuation
            # energy = power (W) * dt (s) * 1,000,000 (uj/J)
            self.sim_energy += current_sim_power * dt * 1_000_000
            # Apply wrapping if it exceeds max range
            if self.sim_energy >= self.max_energy_range:
                self.sim_energy %= self.max_energy_range
        return self.sim_energy

    def get_power_w(self) -> dict:
        now = time.time()
        try:
            current_energy = self.read_energy_uj()
        except Exception as e:
            logger.error(f"Error reading energy for {self.name}: {e}. Forcing mock fallback.")
            self.is_mock = True
            current_energy = self._simulated_read()

        power_w = 0.0
        if self.last_energy is not None and self.last_time is not None:
            dt = now - self.last_time
            if dt > 0:
                delta_energy = current_energy - self.last_energy
                if delta_energy < 0:
                    # Counter wrap around
                    delta_energy += self.max_energy_range
                # Power in Watts = energy in Joules / time in seconds
                # energy in Joules = delta_energy / 1,000,000
                power_w = (delta_energy / 1_000_000.0) / dt

        self.last_energy = current_energy
        self.last_time = now

        return {
            "name": self.name,
            "power_w": round(power_w, 3) if self.last_energy is not None and power_w >= 0 else 0.0,
            "energy_uj": int(current_energy),
            "is_mock": self.is_mock
        }

# Global state
history: List[dict] = []
max_history_len = 300  # 5 minutes at 1s intervals
start_time = time.time()

# Reader instances
# package-0 typically consumes ~35W base, dram consumes ~6W base.
pkg_reader = RAPLReader(RAPL_PATH_PKG, "package-0", 35.0)
dram_reader = RAPLReader(RAPL_PATH_DRAM, "dram", 6.0)

# Cumulative variables for summary
stats = {
    "package": {
        "min_power_w": float("inf"),
        "max_power_w": 0.0,
        "sum_power_w": 0.0,
        "count": 0,
        "total_energy_joules": 0.0
    },
    "dram": {
        "min_power_w": float("inf"),
        "max_power_w": 0.0,
        "sum_power_w": 0.0,
        "count": 0,
        "total_energy_joules": 0.0
    }
}

lock = asyncio.Lock()

async def read_power_loop():
    # Initial read to set baseline
    pkg_reader.get_power_w()
    dram_reader.get_power_w()
    
    last_loop_time = time.time()
    
    while True:
        try:
            await asyncio.sleep(1.0)
            now = time.time()
            dt = now - last_loop_time
            last_loop_time = now
            
            pkg_data = pkg_reader.get_power_w()
            dram_data = dram_reader.get_power_w()
            
            # Update cumulative energy: Joules = Watts * seconds
            pkg_joules = pkg_data["power_w"] * dt
            dram_joules = dram_data["power_w"] * dt
            
            async with lock:
                # Update stats
                for component, data, joules in [("package", pkg_data, pkg_joules), ("dram", dram_data, dram_joules)]:
                    p_val = data["power_w"]
                    s = stats[component]
                    s["count"] += 1
                    s["sum_power_w"] += p_val
                    s["total_energy_joules"] += joules
                    if p_val > 0:  # Avoid recording initial 0.0 or outliers as min
                        s["min_power_w"] = min(s["min_power_w"], p_val)
                    s["max_power_w"] = max(s["max_power_w"], p_val)
                
                # Append to history
                history.append({
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                    "epoch": now,
                    "package_w": pkg_data["power_w"],
                    "dram_w": dram_data["power_w"]
                })
                
                if len(history) > max_history_len:
                    history.pop(0)
                    
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in power reader background loop: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the periodic reader
    task = asyncio.create_task(read_power_loop())
    yield
    # Cleanup
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="Intel RAPL Power Monitor",
    description="FastAPI service monitoring CPU package and DRAM power consumption in real-time.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware to allow connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set base path for files (relative to this app.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Expose static directory if it exists
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    dashboard_path = os.path.join(STATIC_DIR, "dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    return HTMLResponse("<h3>Dashboard not found. Make sure static/dashboard.html is placed correctly.</h3>", status_code=404)

@app.get("/healthz")
async def healthz():
    # Check if sysfs directories exist and if they are readable
    sysfs_accessible = True
    for path in [pkg_reader.energy_path, dram_reader.energy_path]:
        try:
            with open(path, "r") as f:
                f.read(1)
        except Exception:
            sysfs_accessible = False
            break
            
    return {
        "status": "ok",
        "sysfs_accessible": sysfs_accessible,
        "modes": {
            "package": "sysfs" if not pkg_reader.is_mock else "mock",
            "dram": "sysfs" if not dram_reader.is_mock else "mock"
        }
    }

@app.get("/api/power")
async def get_power():
    async with lock:
        if not history:
            return {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "package": {"power_w": 0.0, "is_mock": pkg_reader.is_mock},
                "dram": {"power_w": 0.0, "is_mock": dram_reader.is_mock}
            }
        last_reading = history[-1]
        return {
            "timestamp": last_reading["timestamp"],
            "package": {
                "power_w": last_reading["package_w"],
                "is_mock": pkg_reader.is_mock
            },
            "dram": {
                "power_w": last_reading["dram_w"],
                "is_mock": dram_reader.is_mock
            }
        }

@app.get("/api/summary")
async def get_summary():
    async with lock:
        uptime = time.time() - start_time
        
        pkg_stats = stats["package"]
        dram_stats = stats["dram"]
        
        # Calculate averages safely
        pkg_avg = round(pkg_stats["sum_power_w"] / pkg_stats["count"], 3) if pkg_stats["count"] > 0 else 0.0
        dram_avg = round(dram_stats["sum_power_w"] / dram_stats["count"], 3) if dram_stats["count"] > 0 else 0.0
        
        pkg_min = round(pkg_stats["min_power_w"], 3) if pkg_stats["min_power_w"] != float("inf") else 0.0
        dram_min = round(dram_stats["min_power_w"], 3) if dram_stats["min_power_w"] != float("inf") else 0.0
        
        # Convert total energy to Watt-hours (Joules / 3600)
        pkg_wh = round(pkg_stats["total_energy_joules"] / 3600.0, 6)
        dram_wh = round(dram_stats["total_energy_joules"] / 3600.0, 6)
        
        return {
            "uptime_seconds": int(uptime),
            "package": {
                "average_power_w": pkg_avg,
                "max_power_w": round(pkg_stats["max_power_w"], 3),
                "min_power_w": pkg_min,
                "total_energy_joules": round(pkg_stats["total_energy_joules"], 3),
                "total_energy_wh": pkg_wh,
                "is_mock": pkg_reader.is_mock
            },
            "dram": {
                "average_power_w": dram_avg,
                "max_power_w": round(dram_stats["max_power_w"], 3),
                "min_power_w": dram_min,
                "total_energy_joules": round(dram_stats["total_energy_joules"], 3),
                "total_energy_wh": dram_wh,
                "is_mock": dram_reader.is_mock
            },
            "history": history
        }
