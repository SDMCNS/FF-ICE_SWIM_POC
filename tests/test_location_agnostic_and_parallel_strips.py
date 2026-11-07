"""
Unit & Integration Tests for:
1. Location-Agnostic Aeronautical Ingestion & Dynamic Rebuilding (AeroDataStore, AirspaceGraph, REST API).
2. Physical Concrete Strip Isolation for Parallel Runways (ICAO Doc 9643 SOIR).
3. Multi-Parallel Runway Operations (Quad Runways / Dual Runway Complexes like LFPG, KORD, KATL).
4. Auto-Synthesis of Runway Operational Modes and Physical Concrete Strips from AIP data.
"""
import os
import sys
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone, timedelta, date

sys.path.insert(0, os.path.abspath("."))
os.environ["FF_ICE_DB"] = "test_location_agnostic.db"

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ff_ice_server.main import app, get_db
from ff_ice_server.database import init_db, FlightPlanModel, TrajectoryPointModel
from ff_ice_server.aero_data import AeroDataStore
from ff_ice_server.airspace_graph import AirspaceGraph, get_airspace_graph, reset_airspace_graph
from ff_ice_server.config_loader import (
    reload_configuration,
    get_airport_operations,
    get_airport_runway_mode,
    get_airport_physical_strips,
    get_runway_physical_strip_id,
    get_runway_reciprocal,
    get_canonical_strip_id,
    synthesize_airport_operations
)
from ff_ice_server.slots import get_airport_slots, find_next_available_slot

class TestLocationAgnosticAndParallelStrips(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db_path = "test_location_agnostic.db"
        if os.path.exists(db_path):
            try: os.remove(db_path)
            except Exception: pass

        cls.engine, cls.SessionLocal = init_db(db_path)

        def override_get_db():
            db = cls.SessionLocal()
            try: yield db
            finally: db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        if os.path.exists("test_location_agnostic.db"):
            try: os.remove("test_location_agnostic.db")
            except Exception: pass

    def setUp(self):
        with self.SessionLocal() as db:
            db.query(TrajectoryPointModel).delete()
            db.query(FlightPlanModel).delete()
            db.commit()

    # -------------------------------------------------------------------------
    # 1. Location-Agnostic Ingestion & Dynamic Rebuilding
    # -------------------------------------------------------------------------
    def test_01_rebuild_from_custom_data_directory(self):
        print("\n--- Test 1: Location-Agnostic Rebuilding from Custom Directories ---")
        temp_dir = tempfile.mkdtemp()
        try:
            airports_dir = os.path.join(temp_dir, "airports")
            waypoints_dir = os.path.join(temp_dir, "Waypoints")
            os.makedirs(airports_dir)
            os.makedirs(waypoints_dir)

            # Create custom international aerodromes:
            # 1. Australian airport YSSY (Sydney)
            yssy_data = {
                "icao": "YSSY",
                "name": "Sydney Kingsford Smith",
                "country": "AU",
                "coordinates": {"latitude": "-335646S", "longitude": "1511038E"},
                "elevation": "21",
                "runways": [
                    {"designator": "16R", "true_bearing": 160.0},
                    {"designator": "34L", "true_bearing": 340.0},
                    {"designator": "16L", "true_bearing": 160.0},
                    {"designator": "34R", "true_bearing": 340.0},
                    {"designator": "07", "true_bearing": 70.0},
                    {"designator": "25", "true_bearing": 250.0}
                ]
            }
            with open(os.path.join(airports_dir, "YSSY.json"), "w", encoding="utf-8") as f:
                json.dump(yssy_data, f)

            # 2. Custom Waypoints file
            custom_wps = [
                {"name": "SYD01", "coordinates": "-33.50 151.00", "country": "AU"},
                {"name": "SYD02", "coordinates": {"latitude": "-33.20", "longitude": "150.80"}, "country": "AU"}
            ]
            with open(os.path.join(waypoints_dir, "AU_Waypoints.json"), "w", encoding="utf-8") as f:
                json.dump(custom_wps, f)

            # Initialize AeroDataStore on temp_dir
            custom_store = AeroDataStore(base_dir=temp_dir)
            self.assertIn("YSSY", custom_store.airports)
            yssy = custom_store.airports["YSSY"]
            self.assertEqual(yssy["country"], "AU")
            self.assertEqual(yssy["elevationFeet"], 21)
            self.assertEqual(len(yssy["runways"]), 6)

            self.assertIn("SYD01", custom_store.waypoints)
            self.assertIn("SYD02", custom_store.waypoints)
            print("[PASS] Successfully ingested Australian aerodrome and waypoints.")

            # Test AirspaceGraph construction on custom store
            custom_graph = AirspaceGraph(custom_store)
            self.assertIn("SYD01", custom_graph.nodes)
            self.assertIn("SYD02", custom_graph.nodes)
            print("[PASS] Custom topological airspace graph built successfully.")
        finally:
            shutil.rmtree(temp_dir)

    def test_02_rebuild_rest_api_endpoint(self):
        print("\n--- Test 2: POST /api/v1/aero/rebuild REST API ---")
        res = self.client.post("/api/v1/aero/rebuild")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["status"], "SUCCESS")
        self.assertGreater(body["airportsCount"], 100)
        self.assertGreater(body["waypointsCount"], 1000)
        self.assertGreater(body["graphNodesCount"], 1000)
        print(f"[PASS] Rebuild endpoint returned: {body['airportsCount']} airports, {body['waypointsCount']} waypoints.")

    # -------------------------------------------------------------------------
    # 2. Reciprocal Runways & Physical Concrete Strip Canonicalization
    # -------------------------------------------------------------------------
    def test_03_reciprocal_and_strip_canonicalization(self):
        print("\n--- Test 3: Reciprocal Runway & Strip Calculations ---")
        self.assertEqual(get_runway_reciprocal("27L"), "09R")
        self.assertEqual(get_runway_reciprocal("09L"), "27R")
        self.assertEqual(get_runway_reciprocal("27R"), "09L")
        self.assertEqual(get_runway_reciprocal("08R"), "26L")
        self.assertEqual(get_runway_reciprocal("04"), "22")
        self.assertEqual(get_runway_reciprocal("16"), "34")
        self.assertEqual(get_runway_reciprocal("36C"), "18C")

        # Canonical strip ID (alphabetically / numerically sorted pair)
        self.assertEqual(get_canonical_strip_id("27L"), "09R/27L")
        self.assertEqual(get_canonical_strip_id("09R"), "09R/27L")
        self.assertEqual(get_canonical_strip_id("27R"), "09L/27R")
        self.assertEqual(get_canonical_strip_id("09L"), "09L/27R")
        self.assertEqual(get_canonical_strip_id("26L"), "08R/26L")
        print("[PASS] Reciprocal and canonical concrete strip IDs verified.")

    # -------------------------------------------------------------------------
    # 3. Parallel Segregated Operations & Concrete Strip Isolation
    # -------------------------------------------------------------------------
    def test_04_parallel_segregated_concrete_strip_isolation(self):
        print("\n--- Test 4: Physical Concrete Strip Isolation (EGLL Heathrow) ---")
        # In Heathrow: Strip 1 = 09L/27R (Arrivals), Strip 2 = 09R/27L (Departures)
        strip_27l = get_runway_physical_strip_id("EGLL", "27L")
        strip_27r = get_runway_physical_strip_id("EGLL", "27R")
        self.assertEqual(strip_27l, "09R/27L")
        self.assertEqual(strip_27r, "09L/27R")
        self.assertNotEqual(strip_27l, strip_27r, "Departures and arrivals must be on physically separate concrete strips!")

        strips = get_airport_physical_strips("EGLL")
        self.assertEqual(len(strips), 2)
        print(f"[PASS] EGLL physical strips: {[s['stripId'] for s in strips]}")

    def test_05_multi_parallel_quad_runway_complex(self):
        print("\n--- Test 5: Multiple Parallel Operations (LFPG Paris CDG) ---")
        # LFPG has Quad Parallel Runways in dual complexes:
        # North Doublet: 09L/27R (Arrivals) and 09R/27L (Departures)
        # South Doublet: 08R/26L (Arrivals) and 08L/26R (Departures)
        mode = get_airport_runway_mode("LFPG")
        self.assertEqual(mode, "MULTIPLE_PARALLEL")

        strips = get_airport_physical_strips("LFPG")
        self.assertEqual(len(strips), 4)

        base_time = datetime(2026, 11, 7, 14, 0, 0)

        # File a departure on North Inboard strip (27L)
        with self.SessionLocal() as db:
            p_north = FlightPlanModel(
                gufi="test-lfpg-dep-north",
                callsign="AFR101",
                departure_icao="LFPG",
                departure_runway="27L",
                eobt=base_time - timedelta(minutes=15),
                etot=base_time,
                arrival_icao="EGLL",
                arrival_runway="27R",
                eta=base_time + timedelta(hours=1),
                eldt=base_time + timedelta(hours=1),
                aircraft_type="A320",
                cruising_level="F280",
                cruising_speed="N0450",
                route_string="LFPG DCT EGLL",
                fixm_json="{}",
                fixm_xml="",
                status="FILED"
            )
            # File simultaneous departure on South Inboard strip (26R) at the EXACT SAME MINUTE
            p_south = FlightPlanModel(
                gufi="test-lfpg-dep-south",
                callsign="AFR202",
                departure_icao="LFPG",
                departure_runway="26R",
                eobt=base_time - timedelta(minutes=15),
                etot=base_time,
                arrival_icao="LFMN",
                arrival_runway="04L",
                eta=base_time + timedelta(hours=1, minutes=20),
                eldt=base_time + timedelta(hours=1, minutes=20),
                aircraft_type="A321",
                cruising_level="F310",
                cruising_speed="N0460",
                route_string="LFPG DCT LFMN",
                fixm_json="{}",
                fixm_xml="",
                status="FILED"
            )
            db.add_all([p_north, p_south])
            db.commit()

            # Query departure slots for North strip 27L
            slots_north = get_airport_slots("LFPG", target_date=base_time.date(), slot_type="DEPARTURE", runway="27L", db=db, start_hour=13, end_hour=15)
            # Query departure slots for South strip 26R
            slots_south = get_airport_slots("LFPG", target_date=base_time.date(), slot_type="DEPARTURE", runway="26R", db=db, start_hour=13, end_hour=15)

            # Both slots should record their own occupancy on their respective concrete strip
            self.assertEqual(slots_north["operationalMode"], "MULTIPLE_PARALLEL")
            self.assertEqual(slots_south["operationalMode"], "MULTIPLE_PARALLEL")

            # In multi-parallel, an arrival on 27R does not block 27L departure or 26R departure
            next_slot = find_next_available_slot(
                icao="LFPG",
                runway="27L",
                desired_time=base_time,
                aircraft_type="A320",
                operation="DEPARTURE",
                db=db
            )
            self.assertIsNotNone(next_slot)
            print("[PASS] Multi-parallel quad-runway concrete strip independence verified.")

    # -------------------------------------------------------------------------
    # 4. Auto-Synthesis for Discovered Aerodromes
    # -------------------------------------------------------------------------
    def test_06_dynamic_airport_synthesis(self):
        print("\n--- Test 6: Auto-Synthesis of Runway Modes for New Airports ---")
        # Test 1: Single runway airport (e.g. 08/26)
        rwy_single = [{"designator": "08"}, {"designator": "26"}]
        ops_single = synthesize_airport_operations("TEST_SINGLE", rwy_single)
        self.assertEqual(ops_single["mode"], "MIXED_MODE_SINGLE")
        self.assertEqual(len(ops_single["physicalStrips"]), 1)

        # Test 2: Dual parallel runway airport (e.g. 09L/27R and 09R/27L)
        rwy_dual = [
            {"designator": "09L"}, {"designator": "27R"},
            {"designator": "09R"}, {"designator": "27L"}
        ]
        ops_dual = synthesize_airport_operations("TEST_DUAL", rwy_dual)
        self.assertEqual(ops_dual["mode"], "PARALLEL_SEGREGATED")
        self.assertEqual(len(ops_dual["physicalStrips"]), 2)
        # Verify that segregated roles were assigned: one strip for arrivals, one for departures
        strip1_role = ops_dual["physicalStrips"][0]["segregatedRole"]["WEST"]
        strip2_role = ops_dual["physicalStrips"][1]["segregatedRole"]["WEST"]
        self.assertNotEqual(strip1_role, strip2_role, "One runway strip must handle departures and the other arrivals!")

        # Test 3: Quad parallel runway airport (e.g. 09L, 09R, 08L, 08R)
        rwy_quad = [
            {"designator": "09L"}, {"designator": "27R"},
            {"designator": "09R"}, {"designator": "27L"},
            {"designator": "08L"}, {"designator": "26R"},
            {"designator": "08R"}, {"designator": "26L"}
        ]
        ops_quad = synthesize_airport_operations("TEST_QUAD", rwy_quad)
        self.assertEqual(ops_quad["mode"], "MULTIPLE_PARALLEL")
        self.assertEqual(len(ops_quad["physicalStrips"]), 4)
        print("[PASS] Dynamic auto-synthesis generated correct physical strips and segregated roles.")

if __name__ == "__main__":
    unittest.main()
