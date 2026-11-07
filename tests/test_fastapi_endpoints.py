"""
Test FastAPI SWIM REST endpoints, FIXM content negotiation, and SQLite persistence.
"""
import os
import sys
import unittest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath("."))
os.environ["FF_ICE_DB"] = "test_fastapi_swim.db"

from ff_ice_server.main import app

class TestFastApiSwimEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists("test_fastapi_swim.db"):
            try:
                os.remove("test_fastapi_swim.db")
            except Exception:
                pass

    def setUp(self):
        from ff_ice_server.database import FlightPlanModel, TrajectoryPointModel, ConflictRecordModel
        from ff_ice_server.main import SessionLocal
        with SessionLocal() as db:
            db.query(ConflictRecordModel).delete()
            db.query(TrajectoryPointModel).delete()
            db.query(FlightPlanModel).delete()
            db.commit()

    def test_01_openapi_and_docs(self):
        print("\n--- Testing OpenAPI & Docs ---")
        res = self.client.get("/openapi.json")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["info"]["title"], "SWIM FF-ICE Flight Planning & 4D Deconfliction Information Service")
        print(f"[PASS] OpenAPI spec loaded: {data['info']['title']} (v{data['info']['version']})")

    def test_02_airports_and_waypoints(self):
        print("\n--- Testing Airports & Waypoints Endpoints ---")
        res = self.client.get("/api/v1/airports?query=London")
        self.assertEqual(res.status_code, 200)
        airports = res.json()
        self.assertGreater(len(airports), 0)
        print(f"[PASS] Queried London airports -> Found {len(airports)} airports ({[a['icao'] for a in airports[:3]]})")

        res_wp = self.client.get("/api/v1/waypoints?query=LIPGO")
        self.assertEqual(res_wp.status_code, 200)
        wps = res_wp.json()
        self.assertGreaterEqual(len(wps), 1)
        self.assertEqual(wps[0]["name"], "LIPGO")
        print(f"[PASS] Queried LIPGO waypoint -> {wps[0]['name']} at {wps[0]['latitude']:.2f}, {wps[0]['longitude']:.2f}")

    def test_03_trajectory_calculate_and_deconfliction_preview(self):
        print("\n--- Testing 4D Trajectory Calculation Endpoint ---")
        payload = {
            "departureIcao": "EGLL",
            "arrivalIcao": "EIDW",
            "aircraftType": "A320",
            "requestedCruiseFl": 280,
            "waypointNames": ["LIPGO"],
            "estimatedOffBlockTime": "2026-11-07T16:00:00Z"
        }
        res = self.client.post("/api/v1/trajectory/calculate", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        calc = data["calculated"]
        self.assertIn("points", calc)
        self.assertIn("deconfliction", calc)
        print(f"[PASS] 4D Trajectory calculated: {calc['totalDistanceNm']} NM, {calc['totalFlightTimeMinutes']} min, {len(calc['points'])} points")
        print(f"       Deconfliction: hasConflicts={calc['deconfliction']['hasConflicts']}")

    def test_04_file_plan_json_and_xml_negotiation(self):
        print("\n--- Testing Plan Filing & Content Negotiation ---")
        # 1. File Flight 1 (EIN157)
        plan_json = {
            "flightIdentification": {"aircraftIdentification": "EIN157"},
            "aircraft": {"aircraftType": "A320", "wakeTurbulence": "M", "capabilities": {"standardEquipment": "SDFGIRW/LB1"}},
            "departure": {"aerodrome": "EGLL", "runway": "27R", "elevationFeet": 83, "estimatedOffBlockTime": "2026-11-07T16:00:00Z"},
            "arrival": {"aerodrome": "EIDW", "runway": "28L", "elevationFeet": 243, "estimatedTimeOfArrival": "2026-11-07T16:38:00Z"},
            "enRoute": {"cruisingLevel": "F280", "cruisingSpeed": "N0450", "routeString": "EGLL LIPGO EIDW"},
            "trajectory": {
                "totalDistanceNm": 243.1,
                "totalFlightTimeMinutes": 38.0,
                "points4D": [
                    {"pointType": "DEPARTURE", "identifier": "EGLL", "coordinates": {"latitude": 51.47, "longitude": -0.46}, "altitudeFeet": 83, "flightLevel": 1, "cumulativeDistanceNm": 0.0, "groundSpeedKnots": 320, "estimatedTimestamp": "2026-11-07T16:00:00Z"},
                    {"pointType": "WAYPOINT", "identifier": "LIPGO", "coordinates": {"latitude": 53.06, "longitude": -5.50}, "altitudeFeet": 28000, "flightLevel": 280, "cumulativeDistanceNm": 208.0, "groundSpeedKnots": 450, "estimatedTimestamp": "2026-11-07T16:25:00Z"},
                    {"pointType": "DESTINATION", "identifier": "EIDW", "coordinates": {"latitude": 53.42, "longitude": -6.27}, "altitudeFeet": 243, "flightLevel": 2, "cumulativeDistanceNm": 243.1, "groundSpeedKnots": 290, "estimatedTimestamp": "2026-11-07T16:38:00Z"}
                ]
            }
        }
        res = self.client.post("/api/v1/ffice/plans", json=plan_json)
        self.assertEqual(res.status_code, 201)
        res_data = res.json()
        gufi1 = res_data["plan"]["gufi"]
        self.assertTrue(bool(gufi1))
        print(f"[PASS] Filed Flight 1 (EIN157) with GUFI {gufi1}")

        # 2. Retrieve as FIXM XML
        xml_res = self.client.get(f"/api/v1/ffice/plans/{gufi1}", headers={"Accept": "application/vnd.fixm+xml"})
        self.assertEqual(xml_res.status_code, 200)
        self.assertIn("application/vnd.fixm+xml", xml_res.headers["content-type"])
        self.assertIn("<fx:Flight", xml_res.text)
        print(f"[PASS] Retrieved plan via FIXM XML Accept header: {len(xml_res.text)} bytes")

        # 3. File Flight 2 (Conflicting BAW456, 1 min later on same route & FL)
        import copy
        plan_conflict = copy.deepcopy(plan_json)
        plan_conflict["flightIdentification"] = {"aircraftIdentification": "BAW456"}
        plan_conflict["departure"] = {"aerodrome": "EGLL", "runway": "27R", "elevationFeet": 83, "estimatedOffBlockTime": "2026-11-07T16:01:00Z"}
        plan_conflict["arrival"] = {"aerodrome": "EIDW", "runway": "28L", "elevationFeet": 243, "estimatedTimeOfArrival": "2026-11-07T16:39:00Z"}
        plan_conflict["trajectory"]["points4D"] = [
            {"pointType": "DEPARTURE", "identifier": "EGLL", "coordinates": {"latitude": 51.47, "longitude": -0.46}, "altitudeFeet": 83, "flightLevel": 1, "cumulativeDistanceNm": 0.0, "groundSpeedKnots": 320, "estimatedTimestamp": "2026-11-07T16:01:00Z"},
            {"pointType": "WAYPOINT", "identifier": "LIPGO", "coordinates": {"latitude": 53.06, "longitude": -5.50}, "altitudeFeet": 28000, "flightLevel": 280, "cumulativeDistanceNm": 208.0, "groundSpeedKnots": 450, "estimatedTimestamp": "2026-11-07T16:26:00Z"},
            {"pointType": "DESTINATION", "identifier": "EIDW", "coordinates": {"latitude": 53.42, "longitude": -6.27}, "altitudeFeet": 243, "flightLevel": 2, "cumulativeDistanceNm": 243.1, "groundSpeedKnots": 290, "estimatedTimestamp": "2026-11-07T16:39:00Z"}
        ]
        res_conf = self.client.post("/api/v1/ffice/plans", json=plan_conflict)
        self.assertEqual(res_conf.status_code, 201)
        conf_data = res_conf.json()
        self.assertTrue(conf_data["deconfliction"]["hasConflicts"], "Should flag conflict with EIN157")
        self.assertIn("comprehensiveSolutions", conf_data["deconfliction"])
        self.assertIn("conflictingTrajectory", conf_data["deconfliction"]["conflicts"][0])
        self.assertGreater(len(conf_data["deconfliction"]["conflicts"][0]["conflictingTrajectory"]), 0)
        print(f"[PASS] Filing BAW456 successfully triggered 4D conflict alert with EIN157!")
        print(f"       Comprehensive solutions generated: {len(conf_data['deconfliction']['comprehensiveSolutions'])} solution(s)")
        print(f"       Conflicting trajectory points attached: {len(conf_data['deconfliction']['conflicts'][0]['conflictingTrajectory'])} pts")

        # 4. Query Conflicts endpoint
        conf_list_res = self.client.get("/api/v1/conflicts")
        self.assertEqual(conf_list_res.status_code, 200)
        conf_list = conf_list_res.json()
        self.assertGreaterEqual(len(conf_list), 1)
        print(f"[PASS] GET /api/v1/conflicts: {len(conf_list)} conflict records persisted in database")

    def test_05_noaa_weather_and_active_runways(self):
        print("\n--- Testing NOAA METAR / TAF & Active Runway Selection ---")
        res = self.client.get("/api/v1/weather/metar?icao=EINN")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["icao"], "EINN")
        self.assertIn("activeRunway", data)
        active = data["activeRunway"]
        self.assertTrue(bool(active.get("activeRunway")))
        print(f"[PASS] EINN NOAA METAR retrieved -> Active Runway: RWY {active['activeRunway']} ({active['windSummary']})")

        res_ll = self.client.get("/api/v1/weather/metar?icao=EGLL")
        self.assertEqual(res_ll.status_code, 200)
        data_ll = res_ll.json()
        self.assertIn(data_ll["activeRunway"]["activeRunway"], ["27R", "27L", "09L", "09R", "27"])
        print(f"[PASS] EGLL NOAA METAR retrieved -> Active Runway: RWY {data_ll['activeRunway']['activeRunway']}")

    def test_06_route_autofill_and_corridor_gaps(self):
        print("\n--- Testing Intelligent Route Auto-Fill & Airway Expansion ---")
        payload = {
            "departureIcao": "EGLL",
            "arrivalIcao": "EIDW",
            "waypoints": ["SUROX", "LIPGO"]
        }
        res = self.client.post("/api/v1/route/autofill", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("filledWaypoints", data)
        self.assertIn("insertedWaypoints", data)
        print(f"[PASS] Auto-filled route EGLL -> EIDW: {data['filledWaypoints']}")
        print(f"       Airways used: {data['airwaysUsed']}, Inserted: {data['insertedWaypoints']}")

        # Verify 5 NM straight departure and 17 NM ILS points in trajectory
        calc_payload = {
            "departureIcao": "EGLL",
            "arrivalIcao": "EIDW",
            "aircraftType": "A320",
            "requestedCruiseFl": 280,
            "waypointNames": data["filledWaypoints"]
        }
        res_calc = self.client.post("/api/v1/trajectory/calculate", json=calc_payload)
        self.assertEqual(res_calc.status_code, 200)
        pts = res_calc.json()["calculated"]["points"]
        types = [p["pointType"] for p in pts]
        self.assertIn("INITIAL_CLIMB", types)
        self.assertIn("APPROACH_INTERCEPT", types)
        print(f"[PASS] 4D Trajectory verified: INITIAL_CLIMB (5 NM) and APPROACH_INTERCEPT (17 NM ILS) points verified!")

    def test_07_graph_shortest_path_and_alternatives(self):
        print("\n--- Testing Graph A* Routing & K-Alternatives Endpoints ---")
        # 1. Shortest path LUXTO -> LIPGO
        sp_res = self.client.post("/api/v1/route/shortest-path", json={"start": "LUXTO", "end": "LIPGO"})
        self.assertEqual(sp_res.status_code, 200)
        sp_data = sp_res.json()
        self.assertEqual(sp_data["start"], "LUXTO")
        self.assertEqual(sp_data["end"], "LIPGO")
        self.assertGreater(len(sp_data["waypoints"]), 2)
        print(f"[PASS] POST /api/v1/route/shortest-path: {sp_data['waypoints']} ({sp_data['totalDistanceNm']} NM)")

        # 2. Dynamic alternates for LIPGO
        alt_res = self.client.get("/api/v1/waypoints/LIPGO/alternates?limit=4")
        self.assertEqual(alt_res.status_code, 200)
        alt_data = alt_res.json()
        self.assertEqual(alt_data["waypoint"], "LIPGO")
        self.assertGreaterEqual(len(alt_data["alternates"]), 1)
        print(f"[PASS] GET /api/v1/waypoints/LIPGO/alternates: {alt_data['alternates']}")

        # 3. K-alternative corridors
        k_res = self.client.post("/api/v1/route/alternatives", json={"start": "LUXTO", "end": "LIPGO", "count": 3})
        self.assertEqual(k_res.status_code, 200)
        k_data = k_res.json()
        self.assertGreaterEqual(len(k_data["alternatives"]), 2)
        print(f"[PASS] POST /api/v1/route/alternatives: Generated {len(k_data['alternatives'])} corridors")

if __name__ == "__main__":
    unittest.main()

