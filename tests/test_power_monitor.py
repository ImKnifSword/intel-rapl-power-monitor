import os
import sys
import time
import pytest
from fastapi.testclient import TestClient

# Ensure power_monitor directory is in python search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from power_monitor.app import app, RAPLReader

def test_rapl_reader_simulated():
    """
    Test that RAPLReader works correctly in simulated mode, handles deltas,
    and returns expected dictionary keys and values.
    """
    reader = RAPLReader(
        path="/nonexistent_rapl_path_test", 
        default_name="mock-domain", 
        simulated_base_power=40.0
    )
    
    # First reading sets baseline, should return 0.0 W as time difference is zero
    res1 = reader.get_power_w()
    assert res1["name"] == "mock-domain"
    assert res1["is_mock"] is True
    assert res1["power_w"] == 0.0
    assert res1["energy_uj"] == 100000000
    
    # Sleep to simulate time progression and sample again
    time.sleep(0.1)
    res2 = reader.get_power_w()
    assert res2["is_mock"] is True
    # Power reading should fluctuate around 40W, so check bounds
    assert 25.0 <= res2["power_w"] <= 55.0
    assert res2["energy_uj"] > 100000000

def test_healthz_endpoint():
    """
    Test that /healthz returns 200 OK and contains expected system status info.
    """
    with TestClient(app) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "sysfs_accessible" in data
        assert "modes" in data
        assert "package" in data["modes"]
        assert "dram" in data["modes"]

def test_dashboard_endpoint():
    """
    Test that / serves the static HTML dashboard correctly.
    """
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Intel RAPL Power Monitor" in response.text

def test_api_power_endpoint():
    """
    Test that /api/power returns current power telemetry structure.
    """
    with TestClient(app) as client:
        response = client.get("/api/power")
        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data
        assert "package" in data
        assert "dram" in data
        assert "power_w" in data["package"]
        assert "is_mock" in data["package"]
        assert "power_w" in data["dram"]
        assert "is_mock" in data["dram"]

def test_api_summary_endpoint():
    """
    Test that /api/summary returns historic series data and metrics aggregates.
    """
    with TestClient(app) as client:
        # Allow the background reader loop to tick at least once
        time.sleep(1.2)
        
        response = client.get("/api/summary")
        assert response.status_code == 200
        data = response.json()
        
        # Base metadata checks
        assert "uptime_seconds" in data
        assert "history" in data
        assert isinstance(data["history"], list)
        
        # Package and DRAM metrics validation
        for domain in ["package", "dram"]:
            domain_data = data[domain]
            assert "average_power_w" in domain_data
            assert "max_power_w" in domain_data
            assert "min_power_w" in domain_data
            assert "total_energy_joules" in domain_data
            assert "total_energy_wh" in domain_data
            assert "is_mock" in domain_data
            
            # Check range expectations
            assert domain_data["max_power_w"] >= 0
            assert domain_data["min_power_w"] >= 0
            assert domain_data["total_energy_joules"] >= 0
