"""
Unit & Integration Tests for Operationally Realistic 4D Flight Level Deconfliction.
Verifies:
  1. ICAO Annex 2 Semicircular Rule (Eastbound ODD, Westbound EVEN)
  2. Aircraft certified service ceiling (e.g., AT76 <= FL250, C172 <= FL140, A320 <= FL390)
  3. Route distance aerodynamic climb/descent feasibility (e.g., 60 NM sector <= FL80)
  4. Both individual tactical conflict suggestions and global comprehensive multi-variable solutions.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath("."))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ff_ice_server.database import Base, FlightPlanModel, TrajectoryPointModel
from ff_ice_server.deconfliction import (
    get_realistic_flight_levels,
    ConflictResult,
    solve_comprehensive_deconfliction,
    deconflict_trajectory
)

class TestRealisticDeconfliction(unittest.TestCase):
    def setUp(self):
        # In-memory SQLite for isolated deconfliction testing
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()

    def test_semicircular_rule_eastbound_westbound(self):
        """Verify Eastbound routes get ODD levels and Westbound routes get EVEN levels."""
        # EGLL (51.47, -0.46) to EIDW (53.42, -6.27) is ~301° (Westbound)
        west_res = get_realistic_flight_levels(
            origin_lat=51.47, origin_lon=-0.46,
            dest_lat=53.42, dest_lon=-6.27,
            total_dist_nm=240.0,
            aircraft_type="A320"
        )
        self.assertEqual(west_res["direction"], "WESTBOUND")
        self.assertEqual(west_res["parity"], "EVEN")
        for lvl in west_res["validLevels"]:
            if lvl <= 410:
                self.assertEqual((lvl // 10) % 2, 0, f"Westbound level FL{lvl} must be EVEN")

        # EIDW (53.42, -6.27) to EGLL (51.47, -0.46) is ~117° (Eastbound)
        east_res = get_realistic_flight_levels(
            origin_lat=53.42, origin_lon=-6.27,
            dest_lat=51.47, dest_lon=-0.46,
            total_dist_nm=240.0,
            aircraft_type="A320"
        )
        self.assertEqual(east_res["direction"], "EASTBOUND")
        self.assertEqual(east_res["parity"], "ODD")
        for lvl in east_res["validLevels"]:
            if lvl <= 410:
                self.assertEqual((lvl // 10) % 2, 1, f"Eastbound level FL{lvl} must be ODD")

    def test_aircraft_ceiling_enforcement(self):
        """Verify turboprops like AT76 (ceiling FL250) never receive FL > 250."""
        # AT76 Westbound EGLL -> EIDW (240 NM)
        at76_res = get_realistic_flight_levels(
            origin_lat=51.47, origin_lon=-0.46,
            dest_lat=53.42, dest_lon=-6.27,
            total_dist_nm=240.0,
            aircraft_type="AT76"
        )
        self.assertEqual(at76_res["ceiling"], 250)
        self.assertLessEqual(at76_res["maxEffectiveFl"], 250)
        for lvl in at76_res["validLevels"]:
            self.assertLessEqual(lvl, 250, f"AT76 level FL{lvl} exceeds certified ceiling FL250")

        # C172 (ceiling FL140)
        c172_res = get_realistic_flight_levels(
            origin_lat=51.47, origin_lon=-0.46,
            dest_lat=51.88, dest_lon=-0.37,
            total_dist_nm=35.0,
            aircraft_type="C172"
        )
        self.assertEqual(c172_res["ceiling"], 140)
        for lvl in c172_res["validLevels"]:
            self.assertLessEqual(lvl, 140, f"C172 level FL{lvl} exceeds ceiling FL140")

    def test_journey_distance_feasibility(self):
        """Verify short flights (e.g. 60 NM) cannot climb to high cruise levels like FL340."""
        short_res = get_realistic_flight_levels(
            origin_lat=51.47, origin_lon=-0.46,
            dest_lat=51.50, dest_lon=-2.00,
            total_dist_nm=60.0,
            aircraft_type="A320"
        )
        # 60 NM route allows max ~FL80
        self.assertLessEqual(short_res["maxAchievableFl"], 80)
        for lvl in short_res["validLevels"]:
            self.assertLessEqual(lvl, 80, f"60 NM flight cannot reach FL{lvl}")

    def test_tactical_conflict_result_suggestions(self):
        """Verify ConflictResult._build_suggestions honors parity, ceiling and distance."""
        # Scenario 1: AT76 flying at FL240 (ceiling FL250)
        c1 = ConflictResult(
            conflicting_gufi="fake-gufi-1",
            conflicting_callsign="TRAFFIC1",
            location_lat=52.5,
            location_lon=-3.5,
            time_cpa=datetime.now(),
            min_horizontal_nm=2.0,
            vertical_diff_ft=200,
            severity="CRITICAL",
            description="Test separation loss",
            resolution_advisory="Advisory",
            point_name="LIPGO",
            candidate_fl=240,
            conflict_type="ENROUTE_SEPARATION_LOSS",
            aircraft_type="AT76",
            total_dist_nm=240.0,
            origin_lat=51.47, origin_lon=-0.46,
            dest_lat=53.42, dest_lon=-6.27
        )
        alt_suggestions = [s for s in c1.suggestions if s["type"] == "ALTITUDE_CHANGE"]
        for s in alt_suggestions:
            fl = s["targetFlightLevel"]
            self.assertLessEqual(fl, 250, f"AT76 suggestion FL{fl} exceeds ceiling FL250")
            self.assertEqual((fl // 10) % 2, 0, f"Westbound suggestion FL{fl} must be EVEN")
            # Step climb to FL260 should NOT exist because ceiling is 250
            self.assertNotEqual(fl, 260)

        # Scenario 2: 60 NM flight at FL80 with A320
        c2 = ConflictResult(
            conflicting_gufi="fake-gufi-2",
            conflicting_callsign="TRAFFIC2",
            location_lat=51.48,
            location_lon=-1.0,
            time_cpa=datetime.now(),
            min_horizontal_nm=3.0,
            vertical_diff_ft=300,
            severity="WARNING",
            description="Test short route conflict",
            resolution_advisory="Advisory",
            point_name="MIDPT",
            candidate_fl=80,
            conflict_type="ENROUTE_SEPARATION_LOSS",
            aircraft_type="A320",
            total_dist_nm=60.0,
            origin_lat=51.47, origin_lon=-0.46,
            dest_lat=51.50, dest_lon=-2.00
        )
        alt_s2 = [s for s in c2.suggestions if s["type"] == "ALTITUDE_CHANGE"]
        for s in alt_s2:
            fl = s["targetFlightLevel"]
            self.assertLessEqual(fl, 80, f"Short flight suggestion FL{fl} exceeds distance capacity")
            self.assertEqual((fl // 10) % 2, 0)

    def test_comprehensive_solver_respects_constraints(self):
        """Verify solve_comprehensive_deconfliction vertical strategies respect ceiling and distance."""
        base_t = datetime(2026, 11, 7, 14, 0, 0)
        # Create an existing active flight in DB at FL240
        plan = FlightPlanModel(
            gufi="active-fl240",
            status="FILED",
            callsign="EIN999",
            eobt=base_t,
            eta=base_t + timedelta(minutes=45),
            departure_icao="EGLL",
            arrival_icao="EIDW",
            cruising_level="F240",
            cruising_speed="N0275",
            aircraft_type="AT76",
            route_string="EGLL LIPGO EIDW",
            fixm_json="{}",
            fixm_xml="<xml/>"
        )
        self.db.add(plan)
        # Trajectory point at LIPGO
        pt = TrajectoryPointModel(
            gufi="active-fl240",
            point_index=1,
            point_type="WAYPOINT",
            identifier="LIPGO",
            latitude=53.06,
            longitude=-5.50,
            altitude_feet=24000,
            flight_level=240,
            timestamp=base_t + timedelta(minutes=25)
        )
        self.db.add(pt)
        self.db.commit()

        # Candidate flight: AT76 also planning FL240 at same time
        cand_pts = [
            {"pointType": "DEPARTURE", "identifier": "EGLL", "coordinates": {"latitude": 51.47, "longitude": -0.46}, "altitudeFeet": 83, "flightLevel": 1, "cumulativeDistanceNm": 0.0, "estimatedTimestamp": base_t.isoformat() + "Z"},
            {"pointType": "WAYPOINT", "identifier": "LIPGO", "coordinates": {"latitude": 53.06, "longitude": -5.50}, "altitudeFeet": 24000, "flightLevel": 240, "cumulativeDistanceNm": 208.0, "estimatedTimestamp": (base_t + timedelta(minutes=25)).isoformat() + "Z"},
            {"pointType": "DESTINATION", "identifier": "EIDW", "coordinates": {"latitude": 53.42, "longitude": -6.27}, "altitudeFeet": 243, "flightLevel": 2, "cumulativeDistanceNm": 243.1, "estimatedTimestamp": (base_t + timedelta(minutes=45)).isoformat() + "Z"}
        ]

        outcome = deconflict_trajectory(
            candidate_gufi="cand-at76",
            candidate_callsign="LOG123",
            candidate_points=cand_pts,
            candidate_eobt=base_t,
            candidate_eta=base_t + timedelta(minutes=45),
            db=self.db,
            log_to_db=False,
            aircraft_type="AT76"
        )

        self.assertTrue(outcome.has_conflicts)
        vert_solutions = [s for s in outcome.comprehensive_solutions if s["strategy"] in ("VERTICAL_OPTIMIZATION", "COMBINED_PROFILE")]
        for s in vert_solutions:
            for act in s["actions"]:
                if act["type"] == "SET_ALTITUDE":
                    target_fl = act["targetFlightLevel"]
                    self.assertLessEqual(target_fl, 250, f"Solution {s['id']} proposed FL{target_fl} > AT76 ceiling FL250")
                    self.assertEqual((target_fl // 10) % 2, 0, f"Solution {s['id']} proposed non-even FL{target_fl} for Westbound track")

if __name__ == "__main__":
    unittest.main()
