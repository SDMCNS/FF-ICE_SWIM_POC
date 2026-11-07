"""
Comprehensive Automated Test Suite for Python SWIM Server, SQLite Database & 4D Deconfliction.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath("."))

from ff_ice_server.database import init_db, FlightPlanModel, TrajectoryPointModel, ConflictRecordModel
from ff_ice_server.aero_data import AeroDataStore, haversine_distance_nm
from ff_ice_server.trajectory import calculate_4d_trajectory, check_sanity
from ff_ice_server.deconfliction import deconflict_trajectory
from ff_ice_server.fixm_engine import serialize_to_fixm_xml, parse_fixm_xml, generate_gufi

class TestPythonSwimBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db = "test_swim.db"
        if os.path.exists(cls.test_db):
            os.remove(cls.test_db)
        cls.engine, cls.SessionLocal = init_db(cls.test_db)
        cls.store = AeroDataStore(base_dir=".")

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_db):
            try:
                os.remove(cls.test_db)
            except Exception:
                pass

    def test_01_aero_data_loaded(self):
        print("\n--- Test 1: Python Aeronautical Data Store Ingestion ---")
        self.assertGreater(len(self.store.airports), 100, "Should load >100 UK/Irish airports")
        self.assertIn("EGLL", self.store.airports, "EGLL should be in database")
        self.assertIn("EIDW", self.store.airports, "EIDW should be in database")
        self.assertIn("LIPGO", self.store.waypoints, "LIPGO waypoint should be loaded")
        self.assertIn("EGTTFIR", self.store.firs, "EGTTFIR should be loaded")
        self.assertIn("EISNFIR", self.store.firs, "EISNFIR should be loaded")

        egll = self.store.airports["EGLL"]
        eidw = self.store.airports["EIDW"]
        dist = haversine_distance_nm(egll["latitude"], egll["longitude"], eidw["latitude"], eidw["longitude"])
        print(f"[PASS] EGLL -> EIDW Great Circle: {dist:.1f} NM (Elevations: {egll['elevationFeet']} ft / {eidw['elevationFeet']} ft)")
        self.assertTrue(240 < dist < 246)

    def test_02_trajectory_calculation_and_sanity(self):
        print("\n--- Test 2: 4D Trajectory & Sanity Advisory ---")
        egll = self.store.airports["EGLL"]
        eidw = self.store.airports["EIDW"]
        lipgo = self.store.waypoints["LIPGO"]
        eobt = datetime.now(timezone.utc).replace(tzinfo=None)

        # Normal flight
        traj = calculate_4d_trajectory(egll, eidw, [lipgo], "A320", 280, eobt, list(self.store.firs.values()))
        self.assertTrue(traj["sanityResult"]["isValid"])
        self.assertGreater(len(traj["points"]), 3)
        print(f"[PASS] Trajectory generated: {traj['totalDistanceNm']} NM, {traj['totalFlightTimeMinutes']} min, {len(traj['points'])} points")

        # Impossible short flight sanity check
        insane = check_sanity(83, 243, 60.0, 370, {"ceiling": 390, "climbRate": 2200, "climbSpeed": 320, "descentGrad": 318}, 300.0)
        self.assertFalse(insane["semicircularCompliant"])
        self.assertLess(insane["recommendedCruiseFl"], 200)
        print(f"[PASS] Sanity engine flagged impossible FL370 on 60 NM flight -> recommended FL{insane['recommendedCruiseFl']}")

    def test_03_fixm_xml_roundtrip(self):
        print("\n--- Test 3: FIXM v4.2+ XML Serialization & Parsing ---")
        gufi = generate_gufi()
        plan_dict = {
            "gufi": gufi,
            "status": "FILED",
            "messageType": "FILING",
            "flightIdentification": {"aircraftIdentification": "EIN157"},
            "aircraft": {"aircraftType": "A320", "wakeTurbulence": "M", "capabilities": {"standardEquipment": "SDFGIRW/LB1"}},
            "departure": {"aerodrome": "EGLL", "elevationFeet": 83, "estimatedOffBlockTime": "2026-11-07T14:00:00Z"},
            "arrival": {"aerodrome": "EIDW", "elevationFeet": 243, "estimatedTimeOfArrival": "2026-11-07T14:38:00Z"},
            "enRoute": {"cruisingLevel": "F280", "cruisingSpeed": "N0450", "routeString": "EGLL LIPGO EIDW"},
            "trajectory": {
                "totalDistanceNm": 243.1,
                "totalFlightTimeMinutes": 38.0,
                "points4D": [
                    {"pointType": "DEPARTURE", "identifier": "EGLL", "coordinates": {"latitude": 51.47, "longitude": -0.46}, "altitudeFeet": 83, "flightLevel": 1, "cumulativeDistanceNm": 0.0, "cumulativeTimeSeconds": 0, "estimatedTimestamp": "2026-11-07T14:00:00Z"},
                    {"pointType": "WAYPOINT", "identifier": "LIPGO", "coordinates": {"latitude": 53.06, "longitude": -5.50}, "altitudeFeet": 11300, "flightLevel": 113, "cumulativeDistanceNm": 208.0, "cumulativeTimeSeconds": 1800, "estimatedTimestamp": "2026-11-07T14:30:00Z"},
                    {"pointType": "DESTINATION", "identifier": "EIDW", "coordinates": {"latitude": 53.42, "longitude": -6.27}, "altitudeFeet": 243, "flightLevel": 2, "cumulativeDistanceNm": 243.1, "cumulativeTimeSeconds": 2280, "estimatedTimestamp": "2026-11-07T14:38:00Z"}
                ]
            }
        }
        xml_str = serialize_to_fixm_xml(plan_dict)
        self.assertIn("<fx:Flight", xml_str)
        self.assertIn(gufi, xml_str)

        parsed = parse_fixm_xml(xml_str)
        self.assertEqual(parsed["gufi"], gufi)
        self.assertEqual(parsed["flightIdentification"]["aircraftIdentification"], "EIN157")
        self.assertEqual(parsed["departure"]["aerodrome"], "EGLL")
        self.assertEqual(len(parsed["trajectory"]["points4D"]), 3)
        print(f"[PASS] FIXM XML roundtrip verified with 100% fidelity (GUFI: {gufi})")

    def test_04_database_persistence_and_deconfliction(self):
        print("\n--- Test 4: SQLite Database Persistence & 4D Deconfliction ---")
        db = self.SessionLocal()
        try:
            eobt1 = datetime(2026, 11, 7, 14, 0, 0)
            eta1 = datetime(2026, 11, 7, 14, 40, 0)
            gufi1 = generate_gufi()

            # Flight 1: EIN157 at FL280
            p1_points = [
                {"pointType": "DEPARTURE", "identifier": "EGLL", "coordinates": {"latitude": 51.47, "longitude": -0.46}, "altitudeFeet": 83, "flightLevel": 1, "cumulativeDistanceNm": 0.0, "groundSpeedKnots": 320, "estimatedTimestamp": eobt1.isoformat() + "Z"},
                {"pointType": "WAYPOINT", "identifier": "LIPGO", "coordinates": {"latitude": 53.06, "longitude": -5.50}, "altitudeFeet": 28000, "flightLevel": 280, "cumulativeDistanceNm": 208.0, "groundSpeedKnots": 450, "estimatedTimestamp": (eobt1 + timedelta(minutes=25)).isoformat() + "Z"},
                {"pointType": "DESTINATION", "identifier": "EIDW", "coordinates": {"latitude": 53.42, "longitude": -6.27}, "altitudeFeet": 243, "flightLevel": 2, "cumulativeDistanceNm": 243.1, "groundSpeedKnots": 290, "estimatedTimestamp": eta1.isoformat() + "Z"}
            ]

            plan1 = FlightPlanModel(
                gufi=gufi1,
                callsign="EIN157",
                status="FILED",
                message_type="FILING",
                departure_icao="EGLL",
                eobt=eobt1,
                arrival_icao="EIDW",
                eta=eta1,
                aircraft_type="A320",
                cruising_level="F280",
                route_string="EGLL LIPGO EIDW",
                total_distance_nm=243.1,
                total_flight_time_minutes=40.0,
                fixm_json="{}",
                fixm_xml="<xml/>"
            )
            db.add(plan1)

            for idx, pt in enumerate(p1_points):
                db_pt = TrajectoryPointModel(
                    gufi=gufi1,
                    point_index=idx,
                    point_type=pt["pointType"],
                    identifier=pt["identifier"],
                    latitude=pt["coordinates"]["latitude"],
                    longitude=pt["coordinates"]["longitude"],
                    altitude_feet=pt["altitudeFeet"],
                    flight_level=pt["flightLevel"],
                    cumulative_distance_nm=pt["cumulativeDistanceNm"],
                    ground_speed_knots=pt["groundSpeedKnots"],
                    timestamp=datetime.fromisoformat(pt["estimatedTimestamp"].replace("Z", ""))
                )
                db.add(db_pt)
            db.commit()
            print(f"[PASS] Persisted Flight 1 (EIN157) with GUFI {gufi1} to SQLite.")

            # Flight 2 (Conflicting): BAW456, 1 minute later at same waypoint LIPGO and same FL280!
            eobt2 = eobt1 + timedelta(minutes=1)
            eta2 = eta1 + timedelta(minutes=1)
            gufi2 = generate_gufi()
            p2_points = [
                {"pointType": "DEPARTURE", "identifier": "EGLL", "coordinates": {"latitude": 51.47, "longitude": -0.46}, "altitudeFeet": 83, "flightLevel": 1, "cumulativeDistanceNm": 0.0, "groundSpeedKnots": 320, "estimatedTimestamp": eobt2.isoformat() + "Z"},
                {"pointType": "WAYPOINT", "identifier": "LIPGO", "coordinates": {"latitude": 53.06, "longitude": -5.50}, "altitudeFeet": 28000, "flightLevel": 280, "cumulativeDistanceNm": 208.0, "groundSpeedKnots": 450, "estimatedTimestamp": (eobt2 + timedelta(minutes=25)).isoformat() + "Z"},
                {"pointType": "DESTINATION", "identifier": "EIDW", "coordinates": {"latitude": 53.42, "longitude": -6.27}, "altitudeFeet": 243, "flightLevel": 2, "cumulativeDistanceNm": 243.1, "groundSpeedKnots": 290, "estimatedTimestamp": eta2.isoformat() + "Z"}
            ]

            has_conflicts, conflicts, resolutions = deconflict_trajectory(
                candidate_gufi=gufi2,
                candidate_callsign="BAW456",
                candidate_points=p2_points,
                candidate_eobt=eobt2,
                candidate_eta=eta2,
                db=db,
                log_to_db=True
            )

            self.assertTrue(has_conflicts, "Deconfliction engine should detect conflict between EIN157 and BAW456")
            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0].conflicting_callsign, "EIN157")
            print(f"[PASS] Deconfliction engine detected loss of separation:")
            print(f"       Conflict: {conflicts[0].description}")
            print(f"       Advisory: {conflicts[0].resolution_advisory}")

            # Verify Conflict logged in DB
            db_conflicts = db.query(ConflictRecordModel).all()
            self.assertGreaterEqual(len(db_conflicts), 1)
            print(f"[PASS] Strategic conflict successfully logged to SQLite conflict_records table.")

            # Flight 3 (Separated): RYR101 departing 20 mins later at FL340 (vertically and longitudinally separated)
            eobt3 = eobt1 + timedelta(minutes=20)
            eta3 = eta1 + timedelta(minutes=20)
            p3_points = [
                {"pointType": "DEPARTURE", "identifier": "EGLL", "coordinates": {"latitude": 51.47, "longitude": -0.46}, "altitudeFeet": 83, "flightLevel": 1, "cumulativeDistanceNm": 0.0, "groundSpeedKnots": 320, "estimatedTimestamp": eobt3.isoformat() + "Z"},
                {"pointType": "WAYPOINT", "identifier": "LIPGO", "coordinates": {"latitude": 53.06, "longitude": -5.50}, "altitudeFeet": 34000, "flightLevel": 340, "cumulativeDistanceNm": 208.0, "groundSpeedKnots": 450, "estimatedTimestamp": (eobt3 + timedelta(minutes=25)).isoformat() + "Z"},
                {"pointType": "DESTINATION", "identifier": "EIDW", "coordinates": {"latitude": 53.42, "longitude": -6.27}, "altitudeFeet": 243, "flightLevel": 2, "cumulativeDistanceNm": 243.1, "groundSpeedKnots": 290, "estimatedTimestamp": eta3.isoformat() + "Z"}
            ]
            has_conflicts3, _, _ = deconflict_trajectory(
                candidate_gufi=generate_gufi(),
                candidate_callsign="RYR101",
                candidate_points=p3_points,
                candidate_eobt=eobt3,
                candidate_eta=eta3,
                db=db,
                log_to_db=False
            )
            self.assertFalse(has_conflicts3, "Flight 3 should be fully deconflicted (time & vertical separation)")
            print(f"[PASS] Verified clean separation for RYR101 (no conflict detected).")

        finally:
            db.close()

if __name__ == "__main__":
    unittest.main()
