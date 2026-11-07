"""
Unit and Integration Tests for FF-ICE Flight Plan Lifecycle Management & Automated Background Sweeper.
Tests verify:
1. Operational phase determination: UPCOMING, IN_FLIGHT, COMPLETED, EXPIRED, CANCELLED.
2. GET /api/v1/ffice/plans filtering: only upcoming and active in-flight plans returned by default.
3. Automated background sweeper transitions completed (> ETA + 45m) and expired (> EOBT + 120m) plans.
4. Historical query flag: include_expired=True returns archived/completed plans.
5. POST /api/v1/ffice/plans/sweep endpoint functionality.
"""
import unittest
import json
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from ff_ice_server.database import FlightPlanModel, TrajectoryPointModel, ConflictRecordModel
from ff_ice_server.main import app, SessionLocal
from ff_ice_server.plan_lifecycle import (
    determine_operational_status,
    is_plan_active,
    sweep_expired_flight_plans,
    ETA_BUFFER_MINUTES,
    EOBT_EXPIRED_MINUTES
)

class TestPlanLifecycleAndExpiration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        with SessionLocal() as db:
            db.query(ConflictRecordModel).delete()
            db.query(TrajectoryPointModel).delete()
            db.query(FlightPlanModel).delete()
            db.commit()

    def _create_plan_model(
        self,
        gufi: str,
        callsign: str,
        eobt: datetime,
        eta: datetime,
        status: str = "FILED"
    ) -> FlightPlanModel:
        plan_dict = {
            "gufi": gufi,
            "status": status,
            "messageType": "FILING",
            "flightIdentification": {"aircraftIdentification": callsign},
            "aircraft": {"aircraftType": "A320", "wakeTurbulence": "M"},
            "departure": {"aerodrome": "EGLL", "runway": "27R", "estimatedOffBlockTime": eobt.isoformat() + "Z"},
            "arrival": {"aerodrome": "EIDW", "runway": "28L", "estimatedTimeOfArrival": eta.isoformat() + "Z"},
            "enRoute": {"cruisingLevel": "F280", "cruisingSpeed": "N0450", "routeString": "EGLL LIPGO EIDW"},
            "trajectory": {"totalDistanceNm": 240.0, "totalFlightTimeMinutes": 45.0, "points4D": []}
        }
        return FlightPlanModel(
            gufi=gufi,
            callsign=callsign,
            status=status,
            message_type="FILING",
            departure_icao="EGLL",
            departure_runway="27R",
            eobt=eobt,
            arrival_icao="EIDW",
            arrival_runway="28L",
            eta=eta,
            aircraft_type="A320",
            wake_turbulence="M",
            cruising_level="F280",
            cruising_speed="N0450",
            route_string="EGLL LIPGO EIDW",
            fixm_json=json.dumps(plan_dict),
            fixm_xml="<fx:Flight/>"
        )

    def test_01_operational_phase_determination(self):
        """Verify UPCOMING, IN_FLIGHT, COMPLETED, and EXPIRED state calculations."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # 1. Upcoming flight: EOBT 30 min in future, ETA 75 min in future
        p_upcoming = self._create_plan_model(
            "p1", "EIN001",
            eobt=now + timedelta(minutes=30),
            eta=now + timedelta(minutes=75)
        )
        self.assertEqual(determine_operational_status(p_upcoming, now), "UPCOMING")
        self.assertTrue(is_plan_active(p_upcoming, now))

        # 2. In-flight flight: EOBT 15 min ago, ETA 30 min in future
        p_inflight = self._create_plan_model(
            "p2", "EIN002",
            eobt=now - timedelta(minutes=15),
            eta=now + timedelta(minutes=30)
        )
        self.assertEqual(determine_operational_status(p_inflight, now), "IN_FLIGHT")
        self.assertTrue(is_plan_active(p_inflight, now))

        # 3. Completed flight: EOBT 120 min ago, ETA 60 min ago (> 45 min buffer)
        p_completed = self._create_plan_model(
            "p3", "EIN003",
            eobt=now - timedelta(minutes=120),
            eta=now - timedelta(minutes=60)
        )
        self.assertEqual(determine_operational_status(p_completed, now), "COMPLETED")
        self.assertFalse(is_plan_active(p_completed, now))

        # 4. Expired no-show flight: EOBT 150 min ago (> 120 min threshold), ETA 90 min ago
        p_expired = self._create_plan_model(
            "p4", "EIN004",
            eobt=now - timedelta(minutes=150),
            eta=now - timedelta(minutes=90)
        )
        self.assertEqual(determine_operational_status(p_expired, now), "COMPLETED")

        p_noshow = self._create_plan_model(
            "p5", "EIN005",
            eobt=now - timedelta(minutes=150),
            eta=now - timedelta(minutes=10) # ETA within buffer but EOBT 2.5 hours ago without update
        )
        self.assertEqual(determine_operational_status(p_noshow, now), "EXPIRED")
        self.assertFalse(is_plan_active(p_noshow, now))

    def test_02_database_lifecycle_sweeper(self):
        """Verify sweep_expired_flight_plans marks completed and expired plans in SQLite."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with SessionLocal() as db:
            p_active = self._create_plan_model("g1", "BAW1", now + timedelta(minutes=20), now + timedelta(minutes=60))
            p_inflight = self._create_plan_model("g2", "BAW2", now - timedelta(minutes=10), now + timedelta(minutes=30))
            p_stale = self._create_plan_model("g3", "BAW3", now - timedelta(hours=3), now - timedelta(hours=2))
            p_noshow = self._create_plan_model("g4", "BAW4", now - timedelta(hours=3), now - timedelta(minutes=10))

            db.add_all([p_active, p_inflight, p_stale, p_noshow])
            db.commit()

            # Run sweeper
            result = sweep_expired_flight_plans(db, now)
            self.assertEqual(result["completed"], 1) # g3
            self.assertEqual(result["expired"], 1)   # g4
            self.assertEqual(result["totalSwept"], 2)

            # Verify DB records updated
            g3_db = db.query(FlightPlanModel).filter_by(gufi="g3").first()
            self.assertEqual(g3_db.status, "COMPLETED")
            data_g3 = json.loads(g3_db.fixm_json)
            self.assertEqual(data_g3["status"], "COMPLETED")

            g4_db = db.query(FlightPlanModel).filter_by(gufi="g4").first()
            self.assertEqual(g4_db.status, "EXPIRED")

            g1_db = db.query(FlightPlanModel).filter_by(gufi="g1").first()
            self.assertEqual(g1_db.status, "FILED")

            g2_db = db.query(FlightPlanModel).filter_by(gufi="g2").first()
            self.assertEqual(g2_db.status, "FILED")

    def test_03_active_only_filtering_on_endpoint(self):
        """Verify GET /api/v1/ffice/plans only returns upcoming or in-flight plans by default."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with SessionLocal() as db:
            # Plan A: Upcoming (EOBT in 30 mins)
            pa = self._create_plan_model("ga", "RYR101", now + timedelta(minutes=30), now + timedelta(minutes=80))
            # Plan B: In-Flight (EOBT 10m ago, ETA in 30m)
            pb = self._create_plan_model("gb", "RYR102", now - timedelta(minutes=10), now + timedelta(minutes=30))
            # Plan C: Old completed flight (ETA 2 hours ago)
            pc = self._create_plan_model("gc", "RYR103", now - timedelta(hours=3), now - timedelta(hours=2))

            db.add_all([pa, pb, pc])
            db.commit()

        # Default query (active_only=True)
        res = self.client.get("/api/v1/ffice/plans")
        self.assertEqual(res.status_code, 200)
        plans = res.json()
        gufis = [p["gufi"] for p in plans]

        # Only ga (upcoming) and gb (in-flight) should appear
        self.assertIn("ga", gufis)
        self.assertIn("gb", gufis)
        self.assertNotIn("gc", gufis)
        self.assertEqual(len(plans), 2)

        # Check operationalStatus fields injected
        plan_a = next(p for p in plans if p["gufi"] == "ga")
        self.assertEqual(plan_a["operationalStatus"], "UPCOMING")
        self.assertTrue(plan_a["isUpcoming"])
        self.assertFalse(plan_a["isLikelyInFlight"])

        plan_b = next(p for p in plans if p["gufi"] == "gb")
        self.assertEqual(plan_b["operationalStatus"], "IN_FLIGHT")
        self.assertTrue(plan_b["isLikelyInFlight"])
        self.assertFalse(plan_b["isUpcoming"])

        # Query with include_expired=True
        res_all = self.client.get("/api/v1/ffice/plans?include_expired=true")
        self.assertEqual(res_all.status_code, 200)
        all_plans = res_all.json()
        all_gufis = [p["gufi"] for p in all_plans]
        self.assertIn("gc", all_gufis)
        self.assertEqual(len(all_plans), 3)

    def test_04_manual_sweep_endpoint(self):
        """Verify POST /api/v1/ffice/plans/sweep triggers background sweep."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with SessionLocal() as db:
            p_old = self._create_plan_model("gold", "OLD999", now - timedelta(hours=4), now - timedelta(hours=3))
            db.add(p_old)
            db.commit()

        res = self.client.post("/api/v1/ffice/plans/sweep")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertIn("swept", data)
        self.assertGreaterEqual(data["swept"]["completed"], 1)

    def test_05_swim_status_reports_lifecycle_metrics(self):
        """Verify GET /api/v1/swim/status includes operational phase counts."""
        res = self.client.get("/api/v1/swim/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        stats = data["statistics"]
        self.assertIn("upcomingPlans", stats)
        self.assertIn("inFlightPlans", stats)
        self.assertIn("completedPlans", stats)
        self.assertIn("expiredPlans", stats)
        self.assertIn("lifecyclePolicy", data)
        self.assertEqual(data["lifecyclePolicy"]["etaBufferMinutes"], ETA_BUFFER_MINUTES)
        self.assertTrue(data["lifecyclePolicy"]["backgroundSweeperRunning"])

if __name__ == "__main__":
    unittest.main()
