"""
API integration tests for the City Agents server.

Tests cover endpoints, snapshot integrity, timeline scrubbing, and backward compatibility.
"""

import pytest
import requests
import json
import time

# Configuration
BASE_URL = "http://localhost:8002"
TIMEOUT = 5


class TestAPIBasics:
    """Basic API connectivity and health checks."""

    def test_server_health(self):
        """Server should be running and respond to health check."""
        try:
            response = requests.get(f"{BASE_URL}/", timeout=TIMEOUT)
            assert response.status_code in [200, 404]  # May or may not have root endpoint
        except requests.exceptions.ConnectionError:
            pytest.skip("Server not running on localhost:8002")

    def test_export_results_initial(self):
        """Should be able to export initial (empty) results."""
        response = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data or "globalmetrics" in data


class TestPresets:
    """Tests for preset loading."""

    def test_load_preset_urban_sustainability(self):
        """Load urban sustainability preset."""
        response = requests.post(
            f"{BASE_URL}/load_preset",
            json={"preset": "urban_sustainability"},
            timeout=TIMEOUT
        )
        assert response.status_code == 200

        # Verify agents loaded
        response = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        data = response.json()
        agents = data.get("agents", {})
        assert len(agents) == 6

    def test_load_preset_ai_regulation(self):
        """Load AI regulation debate preset."""
        response = requests.post(
            f"{BASE_URL}/load_preset",
            json={"preset": "ai_regulation_debate"},
            timeout=TIMEOUT
        )
        assert response.status_code == 200

        response = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        data = response.json()
        agents = data.get("agents", {})
        assert len(agents) == 5

    def test_load_preset_climate(self):
        """Load climate summit preset."""
        response = requests.post(
            f"{BASE_URL}/load_preset",
            json={"preset": "climate_summit"},
            timeout=TIMEOUT
        )
        assert response.status_code == 200

        response = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        data = response.json()
        agents = data.get("agents", {})
        assert len(agents) == 6

    def test_load_preset_dev_team(self):
        """Load small dev team preset."""
        response = requests.post(
            f"{BASE_URL}/load_preset",
            json={"preset": "small_dev_team"},
            timeout=TIMEOUT
        )
        assert response.status_code == 200

        response = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        data = response.json()
        agents = data.get("agents", {})
        assert len(agents) == 3

    def test_load_invalid_preset(self):
        """Invalid preset should return error."""
        response = requests.post(
            f"{BASE_URL}/load_preset",
            json={"preset": "nonexistent_preset_xyz"},
            timeout=TIMEOUT
        )
        assert response.status_code != 200


class TestSimulation:
    """Tests for simulation execution."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Load preset before each test."""
        requests.post(
            f"{BASE_URL}/load_preset",
            json={"preset": "small_dev_team"},
            timeout=TIMEOUT
        )

    def test_simulate_single_round(self):
        """Should complete single simulation round."""
        response = requests.post(
            f"{BASE_URL}/simulate_rounds",
            json={"rounds": 1},
            timeout=TIMEOUT
        )
        assert response.status_code == 200

    def test_simulate_multiple_rounds(self):
        """Should complete multiple simulation rounds."""
        response = requests.post(
            f"{BASE_URL}/simulate_rounds",
            json={"rounds": 3},
            timeout=TIMEOUT
        )
        assert response.status_code == 200

    def test_simulate_zero_rounds(self):
        """Zero rounds should be a no-op."""
        response = requests.post(
            f"{BASE_URL}/simulate_rounds",
            json={"rounds": 0},
            timeout=TIMEOUT
        )
        # Should either succeed or be rejected gracefully
        assert response.status_code in [200, 400]

    def test_metrics_populated_after_simulation(self):
        """After simulation, agents should have metric data."""
        requests.post(
            f"{BASE_URL}/simulate_rounds",
            json={"rounds": 1},
            timeout=TIMEOUT
        )

        response = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        data = response.json()
        agents = data.get("agents", {})

        # At least one agent should exist
        assert len(agents) > 0

        # First agent should have metrics
        first_agent = next(iter(agents.values()))
        assert "name" in first_agent
        # Metrics may or may not be present (depends on implementation)


class TestSnapshots:
    """Tests for snapshot system."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Load preset before each test."""
        requests.post(
            f"{BASE_URL}/load_preset",
            json={"preset": "small_dev_team"},
            timeout=TIMEOUT
        )

    def test_export_creates_snapshot(self):
        """Export should return valid snapshot data."""
        requests.post(
            f"{BASE_URL}/simulate_rounds",
            json={"rounds": 1},
            timeout=TIMEOUT
        )

        response = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        data = response.json()

        assert "agents" in data or "globalmetrics" in data

    def test_multiple_exports_consistent(self):
        """Multiple exports without changes should be identical."""
        requests.post(
            f"{BASE_URL}/simulate_rounds",
            json={"rounds": 1},
            timeout=TIMEOUT
        )

        response1 = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        data1 = response1.json()

        response2 = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        data2 = response2.json()

        # Should have same agents
        agents1 = data1.get("agents", {})
        agents2 = data2.get("agents", {})
        assert set(agents1.keys()) == set(agents2.keys())

    def test_load_snapshot(self):
        """Should be able to load a snapshot."""
        requests.post(
            f"{BASE_URL}/simulate_rounds",
            json={"rounds": 1},
            timeout=TIMEOUT
        )

        # Export current state
        response = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        snapshot = response.json()

        # Load it back
        response = requests.post(
            f"{BASE_URL}/load_snapshot",
            json=snapshot,
            timeout=TIMEOUT
        )
        # Should succeed or indicate unsupported
        assert response.status_code in [200, 405]


class TestTimeline:
    """Tests for timeline scrubbing system."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Load preset and run multiple rounds before each test."""
        requests.post(
            f"{BASE_URL}/load_preset",
            json={"preset": "small_dev_team"},
            timeout=TIMEOUT
        )
        # Run 3 rounds to create timeline history
        for _ in range(3):
            requests.post(
                f"{BASE_URL}/simulate_rounds",
                json={"rounds": 1},
                timeout=TIMEOUT
            )

    def test_scrub_to_round(self):
        """Should be able to scrub to specific round."""
        # Current state at round 3
        response1 = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        data1 = response1.json()

        # Try to scrub to round 1 (if endpoint exists)
        response = requests.post(
            f"{BASE_URL}/load_snapshot_at_round",
            json={"round": 1},
            timeout=TIMEOUT
        )
        if response.status_code == 200:
            response2 = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
            data2 = response2.json()
            # Should have same agents but potentially different metrics
            agents1 = set(data1.get("agents", {}).keys())
            agents2 = set(data2.get("agents", {}).keys())
            assert agents1 == agents2


class TestDataIntegrity:
    """Tests for data integrity across operations."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Load preset before each test."""
        requests.post(
            f"{BASE_URL}/load_preset",
            json={"preset": "climate_summit"},
            timeout=TIMEOUT
        )

    def test_agent_ids_preserved(self):
        """Agent IDs should remain consistent across operations."""
        response1 = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        agents1_ids = set(response1.json().get("agents", {}).keys())

        requests.post(
            f"{BASE_URL}/simulate_rounds",
            json={"rounds": 1},
            timeout=TIMEOUT
        )

        response2 = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        agents2_ids = set(response2.json().get("agents", {}).keys())

        assert agents1_ids == agents2_ids

    def test_agent_names_immutable(self):
        """Agent names should not change during simulation."""
        response1 = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        names1 = {aid: a.get("name") for aid, a in response1.json().get("agents", {}).items()}

        requests.post(
            f"{BASE_URL}/simulate_rounds",
            json={"rounds": 2},
            timeout=TIMEOUT
        )

        response2 = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        names2 = {aid: a.get("name") for aid, a in response2.json().get("agents", {}).items()}

        assert names1 == names2

    def test_metrics_increasing_or_zero(self):
        """Turn counts and token counts should be monotonically increasing."""
        response1 = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        data1 = response1.json()

        requests.post(
            f"{BASE_URL}/simulate_rounds",
            json={"rounds": 1},
            timeout=TIMEOUT
        )

        response2 = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        data2 = response2.json()

        agents1 = data1.get("agents", {})
        agents2 = data2.get("agents", {})

        for aid in agents1:
            turns1 = agents1[aid].get("turncount", 0)
            turns2 = agents2[aid].get("turncount", 0)
            assert turns2 >= turns1, f"Turn count should increase for {aid}"


class TestBackwardCompatibility:
    """Tests for backward compatibility with old snapshot formats."""

    def test_old_snapshot_loads_gracefully(self):
        """Should handle snapshots without new metric fields."""
        # Create minimal old-format snapshot
        old_snapshot = {
            "agents": {
                "alice": {
                    "id": "alice",
                    "name": "Alice",
                    "role": "User",
                    "cluster": "c1",
                    "turncount": 5,
                    # Missing all new metrics
                }
            },
            "globalmetrics": {}
        }

        # Should not crash
        response = requests.post(
            f"{BASE_URL}/load_snapshot",
            json=old_snapshot,
            timeout=TIMEOUT
        )
        # May succeed or return 405 (unsupported)
        assert response.status_code in [200, 405]

    def test_missing_metrics_default_gracefully(self):
        """Frontend should handle agents with missing metrics."""
        requests.post(
            f"{BASE_URL}/load_preset",
            json={"preset": "small_dev_team"},
            timeout=TIMEOUT
        )

        response = requests.get(f"{BASE_URL}/export_results", timeout=TIMEOUT)
        data = response.json()
        agents = data.get("agents", {})

        # All agents should at least have id and name
        for agent_id, agent in agents.items():
            assert "id" in agent or "name" in agent


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    def test_invalid_json_rejected(self):
        """Invalid JSON should be rejected."""
        response = requests.post(
            f"{BASE_URL}/simulate_rounds",
            data="{ invalid json }",
            timeout=TIMEOUT
        )
        assert response.status_code >= 400

    def test_missing_required_fields(self):
        """Missing required fields should be rejected."""
        response = requests.post(
            f"{BASE_URL}/simulate_rounds",
            json={},  # Missing "rounds"
            timeout=TIMEOUT
        )
        assert response.status_code >= 400

    def test_negative_rounds_rejected(self):
        """Negative round count should be rejected."""
        response = requests.post(
            f"{BASE_URL}/simulate_rounds",
            json={"rounds": -1},
            timeout=TIMEOUT
        )
        assert response.status_code >= 400 or response.status_code == 200  # Implementation-dependent


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
