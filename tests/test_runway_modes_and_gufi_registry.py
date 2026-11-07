"""
Unit & Integration Tests for:
1. Parallel Segregated vs Single Runway Mixed-Mode Operations (ICAO Doc 9643 SOIR & Doc 4444).
2. EOBT vs ETOT Runway Slotting & 4D Trajectory Alignment (EXOT / EXIT).
3. Central GUFI Registry Demonstration Service (ICAO Doc 9965 Central Register Placeholder).
4. SWIM Yellow Profile Service Description & Delivery Requirements (TI-Profile Yellow v2.0 & RFC 7807).
"""
import os
import sys
import unittest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath("."))
os.environ["FF_ICE_DB"] = "test_runways_gufi.db"

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ff_ice_server.main import app, get_db
from ff_ice_server.database import init_db, FlightPlanModel, TrajectoryPointModel
from ff_ice_server.slots import get_airport_slots, find_next_available_slot
from ff_ice_server.trajectory import calculate_4d_trajectory
from ff_ice_server.aero_data import AeroDataStore
from ff_ice_server.gufi_registry import (
    allocate_central_gufi,
    verify_central_gufi,
    commit_central_gufi,
    release_central_gufi,
    list_central_gufis
)
from ff_ice_server.config_loader import (
    get_airport_runway_mode,
    is_parallel_segregated_airport,
    get_airport_taxi_out_minutes,
    get_airport_taxi_in_minutes,
    get_airport_mixed_mode_occupancy_buffer
)

class TestRunwayModesAndGufiRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db_path = "test_runways_gufi.db"
        if os.path.exists(db_path):
            try: os.remove(db_path)
            except Exception: pass

        cls.engine, cls.SessionLocal = init_db(db_path)

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
        cls.store = AeroDataStore()

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        if os.path.exists("test_runways_gufi.db"):
            try: os.remove("test_runways_gufi.db")
            except Exception: pass

    def setUp(self):
        # Clear database between tests
        with self.SessionLocal() as db:
            db.query(TrajectoryPointModel).delete()
            db.query(FlightPlanModel).delete()
            db.commit()

    # -------------------------------------------------------------------------
    # 1. Parallel Runway vs Single Runway Operational Modes
    # -------------------------------------------------------------------------
    def test_01_airport_runway_mode_configuration(self):
        print("\n--- Test 1: Airport Operations Configuration ---")
        # EGLL (Heathrow) & EIDW (Dublin) have parallel segregated runways
        self.assertEqual(get_airport_runway_mode("EGLL"), "PARALLEL_SEGREGATED")
        self.assertTrue(is_parallel_segregated_airport("EGLL"))
        self.assertEqual(get_airport_runway_mode("EIDW"), "PARALLEL_SEGREGATED")
        self.assertTrue(is_parallel_segregated_airport("EIDW"))

        # EGKK (Gatwick) has a single operational runway (08R/26L) in mixed mode
        self.assertEqual(get_airport_runway_mode("EGKK"), "MIXED_MODE_SINGLE")
        self.assertFalse(is_parallel_segregated_airport("EGKK"))

        # Check taxi times & buffer
        self.assertGreaterEqual(get_airport_taxi_out_minutes("EGLL"), 15)
        self.assertGreaterEqual(get_airport_taxi_in_minutes("EGLL"), 8)
        self.assertGreaterEqual(get_airport_mixed_mode_occupancy_buffer("EGKK"), 60)
        print("[PASS] Configured operational modes correctly identified.")

    def test_02_parallel_segregated_runway_capacity(self):
        print("\n--- Test 2: Parallel Segregated Runway Capacity (EGLL) ---")
        base_time = datetime(2026, 11, 7, 10, 0, 0)

        # File a departure on EGLL 27R
        with self.SessionLocal() as db:
            p1 = FlightPlanModel(
                gufi="test-egll-dep-1",
                callsign="BAW101",
                departure_icao="EGLL",
                departure_runway="27R",
                eobt=base_time - timedelta(minutes=20),
                etot=base_time,
                arrival_icao="EIDW",
                arrival_runway="28L",
                eta=base_time + timedelta(minutes=50),
                eldt=base_time + timedelta(minutes=50),
                aircraft_type="B77W", # Heavy
                wake_turbulence="H",
                cruising_level="F360",
                cruising_speed="N0460",
                route_string="EGLL DCT EIDW",
                fixm_json="{}",
                fixm_xml="",
                status="FILED"
            )
            # File an arrival on EGLL parallel runway 27L at the EXACT SAME TIME
            p2 = FlightPlanModel(
                gufi="test-egll-arr-1",
                callsign="AAL100",
                departure_icao="KJFK",
                departure_runway="04L",
                eobt=base_time - timedelta(hours=7),
                etot=base_time - timedelta(hours=6, minutes=40),
                arrival_icao="EGLL",
                arrival_runway="27L", # Parallel runway!
                eta=base_time,
                eldt=base_time,
                aircraft_type="A359", # Heavy
                wake_turbulence="H",
                cruising_level="F380",
                cruising_speed="N0470",
                route_string="KJFK DCT EGLL",
                fixm_json="{}",
                fixm_xml="",
                status="FILED"
            )
            db.add_all([p1, p2])
            db.commit()

            # Because EGLL is PARALLEL_SEGREGATED, the 27L arrival does NOT block 27R departure
            slots_27r = get_airport_slots("EGLL", target_date=base_time.date(), slot_type="DEPARTURE", db=db, start_hour=9, end_hour=11)
            self.assertEqual(slots_27r["operationalMode"], "PARALLEL_SEGREGATED")
            # The departure is occupied
            self.assertGreaterEqual(slots_27r["occupiedCount"], 1)

            # Check next departure slot on 27R behind Heavy BAW101:
            # Medium aircraft behind Heavy requires 120s wake separation on the SAME runway
            next_slot = find_next_available_slot(
                icao="EGLL",
                runway="27R",
                desired_time=base_time,
                aircraft_type="A320", # Medium
                operation="DEPARTURE",
                db=db
            )
            slot_etot = datetime.fromisoformat(next_slot["slotTimeEtot"].replace("Z", ""))
            delta_sec = (slot_etot - base_time).total_seconds()
            self.assertGreaterEqual(delta_sec, 120, "Medium departure behind Heavy requires at least 120s wake spacing")
            print(f"[PASS] Parallel segregated separation confirmed. Next ETOT is +{delta_sec}s.")

    def test_03_single_runway_mixed_mode_interleaving(self):
        print("\n--- Test 3: Single Runway Mixed-Mode Interleaving (EGKK) ---")
        base_time = datetime(2026, 11, 7, 12, 0, 0)

        # File an arrival on Gatwick 26L (Heavy B789)
        with self.SessionLocal() as db:
            arr_plan = FlightPlanModel(
                gufi="test-egkk-arr-1",
                callsign="VIR11",
                departure_icao="KMCO",
                departure_runway="17R",
                eobt=base_time - timedelta(hours=8),
                etot=base_time - timedelta(hours=7, minutes=45),
                arrival_icao="EGKK",
                arrival_runway="26L",
                eta=base_time,
                eldt=base_time,
                aircraft_type="B789", # Heavy
                wake_turbulence="H",
                cruising_level="F390",
                cruising_speed="N0480",
                route_string="KMCO DCT EGKK",
                fixm_json="{}",
                fixm_xml="",
                status="FILED"
            )
            db.add(arr_plan)
            db.commit()

            # Gatwick is MIXED_MODE_SINGLE: Arrivals and Departures share 26L
            slots = get_airport_slots("EGKK", target_date=base_time.date(), slot_type="DEPARTURE", db=db, start_hour=11, end_hour=13)
            self.assertEqual(slots["operationalMode"], "MIXED_MODE_SINGLE")
            # In single runway mixed mode, the arrival IS counted against departure slots
            self.assertGreaterEqual(slots["occupiedCount"], 1)

            # Now find a departure slot for an A320 wanting to depart at base_time
            # In mixed mode, the runway occupancy buffer (90s for EGKK) + Heavy wake penalty (30s) = 120s buffer
            next_dep = find_next_available_slot(
                icao="EGKK",
                runway="26L",
                desired_time=base_time,
                aircraft_type="A320",
                operation="DEPARTURE",
                db=db
            )
            dep_etot = datetime.fromisoformat(next_dep["slotTimeEtot"].replace("Z", ""))
            delta_sec = (dep_etot - base_time).total_seconds()
            self.assertGreaterEqual(delta_sec, 90, "Single runway mixed mode must enforce occupancy buffer between arrival and departure")
            print(f"[PASS] Single runway mixed mode interleaving enforced buffer of {delta_sec}s.")

    # -------------------------------------------------------------------------
    # 2. EOBT vs ETOT Reconciliation & 4D Trajectory
    # -------------------------------------------------------------------------
    def test_04_eobt_vs_etot_calculation_backwards(self):
        print("\n--- Test 4: ETOT Key Detail Working Backwards to EOBT ---")
        dep_ap = self.store.airports["EGLL"]
        arr_ap = self.store.airports["EIDW"]
        wps = [self.store.waypoints["LIPGO"]]

        # Dispatcher specifies desired wheels-off ETOT: 14:00:00
        desired_etot = datetime(2026, 11, 7, 14, 0, 0)
        exot_expected = get_airport_taxi_out_minutes("EGLL") # 20 mins

        res = calculate_4d_trajectory(
            dep_airport=dep_ap,
            arr_airport=arr_ap,
            waypoints=wps,
            aircraft_type="A320",
            requested_fl=280,
            etot_dt=desired_etot
        )

        calc_etot = datetime.fromisoformat(res["etot"].replace("Z", ""))
        calc_eobt = datetime.fromisoformat(res["eobt"].replace("Z", ""))

        self.assertEqual(calc_etot, desired_etot)
        # EOBT must be ETOT - EXOT (14:00 - 20min = 13:40)
        self.assertEqual(calc_eobt, desired_etot - timedelta(minutes=exot_expected))
        self.assertEqual(res["taxiOutMinutes"], exot_expected)

        # First trajectory point airborne at runway wheels-off (ETOT)
        first_pt_time = datetime.fromisoformat(res["points"][0]["estimatedTimestamp"].replace("Z", ""))
        self.assertEqual(first_pt_time, desired_etot)

        # Arrival: ELDT touchdown and EIBT gate in-block
        calc_eldt = datetime.fromisoformat(res["eldt"].replace("Z", ""))
        calc_eibt = datetime.fromisoformat(res["eibt"].replace("Z", ""))
        exit_expected = get_airport_taxi_in_minutes("EIDW") # 10 mins
        self.assertEqual(calc_eibt, calc_eldt + timedelta(minutes=exit_expected))
        print(f"[PASS] ETOT {calc_etot.isoformat()} correctly derived off-stand EOBT {calc_eobt.isoformat()} (-{exot_expected}m).")

    # -------------------------------------------------------------------------
    # 3. Central GUFI Registry & Filing Coordination
    # -------------------------------------------------------------------------
    def test_05_central_gufi_allocation_and_verification(self):
        print("\n--- Test 5: Central GUFI Registry Allocation ---")
        # 1. Allocate GUFI centrally
        res = self.client.post("/api/v1/registry/gufi/allocate", json={
            "callsign": "RYR204",
            "departureIcao": "EIDW",
            "arrivalIcao": "EGSS",
            "estimatedOffBlockTime": "2026-11-07T15:00:00Z"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        gufi = data["gufi"]
        self.assertTrue(gufi.startswith("urn:uuid:"))
        self.assertEqual(data["status"], "ALLOCATED")
        self.assertTrue(data["isCentralPlaceholder"])

        # 2. Verify GUFI via Central Registry endpoint
        ver_res = self.client.get(f"/api/v1/registry/gufi/{gufi}/verify")
        self.assertEqual(ver_res.status_code, 200)
        ver_data = ver_res.json()
        self.assertTrue(ver_data["isValid"])
        self.assertTrue(ver_data["isRegistered"])

        # 3. Verify unallocated GUFI returns invalid
        fake_res = self.client.get("/api/v1/registry/gufi/urn:uuid:00000000-dead-beef-0000-000000000000/verify")
        self.assertEqual(fake_res.status_code, 200)
        self.assertFalse(fake_res.json()["isValid"])
        print(f"[PASS] Centrally allocated {gufi} verified successfully.")

    def test_06_plan_filing_registers_and_commits_gufi(self):
        print("\n--- Test 6: Flight Plan Filing Transitions GUFI to COMMITTED ---")
        plan = {
            "flightIdentification": {"aircraftIdentification": "EIN202"},
            "aircraft": {"aircraftType": "A320", "wakeTurbulence": "M"},
            "departure": {
                "aerodrome": "EIDW",
                "runway": "28L",
                "estimatedTakeOffTime": "2026-11-07T16:00:00Z"
            },
            "arrival": {
                "aerodrome": "EGLL",
                "runway": "27R",
                "estimatedTimeOfArrival": "2026-11-07T16:50:00Z"
            },
            "enRoute": {"cruisingLevel": "F280", "cruisingSpeed": "N0450", "routeString": "EIDW LIPGO EGLL"},
            "trajectory": {
                "points4D": [
                    {"pointType": "DEPARTURE", "identifier": "EIDW", "coordinates": {"latitude": 53.42, "longitude": -6.27}, "altitudeFeet": 243, "flightLevel": 2, "estimatedTimestamp": "2026-11-07T16:00:00Z"},
                    {"pointType": "DESTINATION", "identifier": "EGLL", "coordinates": {"latitude": 51.47, "longitude": -0.46}, "altitudeFeet": 83, "flightLevel": 1, "estimatedTimestamp": "2026-11-07T16:50:00Z"}
                ]
            }
        }

        res = self.client.post("/api/v1/ffice/plans", json=plan)
        self.assertEqual(res.status_code, 201)
        res_data = res.json()["plan"]
        gufi = res_data["gufi"]

        # Check that central registry has it as COMMITTED
        ver = self.client.get(f"/api/v1/registry/gufi/{gufi}/verify").json()
        self.assertTrue(ver["isValid"])
        self.assertEqual(ver["record"]["status"], "COMMITTED")

        # Now cancel plan
        del_res = self.client.delete(f"/api/v1/ffice/plans/{gufi}")
        self.assertEqual(del_res.status_code, 200)

        # Check that registry now marks it CANCELLED
        ver_post = self.client.get(f"/api/v1/registry/gufi/{gufi}/verify").json()
        self.assertEqual(ver_post["record"]["status"], "CANCELLED")
        print(f"[PASS] Complete lifecycle (ALLOCATED -> COMMITTED -> CANCELLED) confirmed.")

    # -------------------------------------------------------------------------
    # 4. SWIM Yellow Profile Conformance & Error Delivery
    # -------------------------------------------------------------------------
    def test_07_swim_yellow_profile_service_description(self):
        print("\n--- Test 7: SWIM Yellow Profile Service Description Document (SDD) ---")
        res = self.client.get("/api/v1/swim/service-description")
        self.assertEqual(res.status_code, 200)
        sdd = res.json()

        ident = sdd["serviceIdentification"]
        self.assertEqual(ident["serviceUrn"], "urn:swim:service:ffice:flight-planning:v1")
        self.assertIn("EUROCONTROL SWIM Yellow Profile", ident["conformanceProfile"])

        tech = sdd["serviceTechnicalInterface"]
        self.assertIn("application/vnd.fixm+xml", tech["supportedPayloadFormats"])
        self.assertIn("application/problem+json", tech["supportedPayloadFormats"])

        # Check SLA and Central Registry placeholder notice
        self.assertIn("centralRegistryFederation", sdd)
        self.assertEqual(sdd["centralRegistryFederation"]["status"], "DEMONSTRATION_PLACEHOLDER")
        print("[PASS] Yellow Profile Service Description Document verified.")

    def test_08_swim_health_and_operational_status(self):
        print("\n--- Test 8: SWIM Health & Status Endpoints ---")
        h_res = self.client.get("/api/v1/swim/health")
        self.assertEqual(h_res.status_code, 200)
        h_data = h_res.json()
        self.assertEqual(h_data["status"], "HEALTHY")
        self.assertTrue(h_data["yellowProfileCompliant"])
        self.assertTrue(h_data["databaseConnected"])

        s_res = self.client.get("/api/v1/swim/status")
        self.assertEqual(s_res.status_code, 200)
        s_data = s_res.json()
        self.assertIn("PARALLEL_SEGREGATED", s_data["runwayModesSupported"])
        self.assertIn("MIXED_MODE_SINGLE", s_data["runwayModesSupported"])
        print("[PASS] SWIM Health and Operational Status endpoints verified.")

    def test_09_rfc7807_problem_details_error_handling(self):
        print("\n--- Test 9: RFC 7807 Problem Details on HTTP Errors ---")
        # Request non-existent plan
        res = self.client.get("/api/v1/ffice/plans/non-existent-gufi", headers={"Accept": "application/problem+json"})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.headers.get("content-type"), "application/problem+json")
        body = res.json()
        self.assertEqual(body["status"], 404)
        self.assertTrue(body["type"].startswith("urn:swim:error:404"))
        self.assertEqual(body["instance"], "/api/v1/ffice/plans/non-existent-gufi")
        print(f"[PASS] RFC 7807 problem details response returned as required by Yellow Profile.")

if __name__ == "__main__":
    unittest.main()
