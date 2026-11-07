"""
Comprehensive unit tests for Airport Runway Slot Management and ICAO Doc 4444 Wake Separation.
Verifies:
1. ICAO Doc 4444 Wake Turbulence separation intervals (departure) and distance minima (approach).
2. Vertical separation rule: Aircraft can occupy the exact same horizontal position if >= 1,000 ft vertically separated.
3. En-route 5 NM horizontal rule when < 1,000 ft vertical separation.
4. Approach 3 NM rule (or wake separation minimum).
5. Airport runway slot scheduling and capacity board.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from datetime import datetime, timezone, timedelta

from ff_ice_server.slots import (
    get_wake_category,
    get_departure_wake_interval,
    get_approach_wake_separation,
    get_airport_slots,
    find_next_available_slot,
    DEPARTURE_WAKE_INTERVAL_SEC,
    APPROACH_WAKE_SEPARATION_NM
)
from ff_ice_server.deconfliction import (
    deconflict_trajectory,
    interpolate_trajectory_at_time
)
from ff_ice_server.database import init_db, FlightPlanModel, TrajectoryPointModel

engine, SessionLocal = init_db("ff_ice.db")


class TestWakeTurbulenceAndSlots(unittest.TestCase):

    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_wake_categories(self):
        self.assertEqual(get_wake_category("B77W"), "H")
        self.assertEqual(get_wake_category("B744"), "H")
        self.assertEqual(get_wake_category("A359"), "H")
        self.assertEqual(get_wake_category("A320"), "M")
        self.assertEqual(get_wake_category("B738"), "M")
        self.assertEqual(get_wake_category("E190"), "M")
        self.assertEqual(get_wake_category("AT76"), "M")
        self.assertEqual(get_wake_category("C172"), "L")
        self.assertEqual(get_wake_category("PC12"), "L")

    def test_departure_wake_intervals(self):
        """ICAO Doc 4444 Chapter 5 departure vortex time intervals."""
        # Heavy followed by Heavy: 120s
        self.assertEqual(get_departure_wake_interval("H", "H"), 120)
        # Heavy followed by Medium: 120s
        self.assertEqual(get_departure_wake_interval("H", "M"), 120)
        # Heavy followed by Light: 180s
        self.assertEqual(get_departure_wake_interval("H", "L"), 180)
        # Medium followed by Light: 120s
        self.assertEqual(get_departure_wake_interval("M", "L"), 120)
        # Medium followed by Medium: 90s (runway occupancy standard)
        self.assertEqual(get_departure_wake_interval("M", "M"), 90)
        # Light followed by Light: 90s
        self.assertEqual(get_departure_wake_interval("L", "L"), 90)

    def test_approach_wake_separation(self):
        """ICAO Doc 4444 Chapter 8 radar approach wake separation minima."""
        # Heavy followed by Heavy: 4.0 NM
        self.assertEqual(get_approach_wake_separation("H", "H"), 4.0)
        # Heavy followed by Medium: 5.0 NM
        self.assertEqual(get_approach_wake_separation("H", "M"), 5.0)
        # Heavy followed by Light: 6.0 NM
        self.assertEqual(get_approach_wake_separation("H", "L"), 6.0)
        # Medium followed by Light: 5.0 NM
        self.assertEqual(get_approach_wake_separation("M", "L"), 5.0)
        # Medium followed by Medium: 3.0 NM
        self.assertEqual(get_approach_wake_separation("M", "M"), 3.0)
        # Light followed by Light: 3.0 NM
        self.assertEqual(get_approach_wake_separation("L", "L"), 3.0)

    def test_vertical_separation_exemption(self):
        """
        Critical rule: Aircraft CAN occupy the exact same horizontal position
        if they are adequately separated vertically (>= 1,000 ft).
        """
        t_base = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        t_overflight = t_base + timedelta(minutes=20)
        t_eta = t_base + timedelta(minutes=50)

        # Candidate points: en-route at FL300 (30,000 ft) over LIPGO
        candidate_points = [
            {
                "identifier": "EGLL",
                "pointType": "DEPARTURE",
                "coordinates": {"latitude": 51.4700, "longitude": -0.4543},
                "altitudeFeet": 83,
                "flightLevel": 1,
                "estimatedTimestamp": t_base.isoformat()
            },
            {
                "identifier": "LIPGO",
                "pointType": "WAYPOINT",
                "coordinates": {"latitude": 53.0, "longitude": -4.0},
                "altitudeFeet": 30000,
                "flightLevel": 300,
                "estimatedTimestamp": t_overflight.isoformat()
            },
            {
                "identifier": "EIDW",
                "pointType": "DESTINATION",
                "coordinates": {"latitude": 53.4213, "longitude": -6.2701},
                "altitudeFeet": 242,
                "flightLevel": 2,
                "estimatedTimestamp": t_eta.isoformat()
            }
        ]

        # Clean existing test flights
        self.db.query(TrajectoryPointModel).filter(TrajectoryPointModel.gufi.in_(["test-gufi-vert-sep", "test-gufi-loss-vert-sep"])).delete()
        self.db.query(FlightPlanModel).filter(FlightPlanModel.gufi.in_(["test-gufi-vert-sep", "test-gufi-loss-vert-sep"])).delete()
        self.db.commit()

        # Flight 2 at identical coordinates and time, but FL320 (32,000 ft -> delta 2,000 ft >= 1,000 ft)
        plan2 = FlightPlanModel(
            gufi="test-gufi-vert-sep",
            callsign="TEST02",
            status="FILED",
            departure_icao="EGLL",
            departure_runway="27R",
            arrival_icao="EIDW",
            arrival_runway="28L",
            eobt=t_base,
            eta=t_eta,
            aircraft_type="A320",
            cruising_level="F320",
            route_string="EGLL LIPGO EIDW",
            fixm_json="{}",
            fixm_xml="<xml/>"
        )
        self.db.add(plan2)
        pt2 = TrajectoryPointModel(
            gufi="test-gufi-vert-sep",
            point_index=1,
            point_type="WAYPOINT",
            identifier="LIPGO",
            latitude=53.0,
            longitude=-4.0,
            altitude_feet=32000,
            flight_level=320,
            timestamp=t_overflight
        )
        self.db.add(pt2)
        self.db.commit()

        # Test deconfliction: candidate (30,000 ft) vs TEST02 (32,000 ft)
        outcome = deconflict_trajectory(
            candidate_gufi="test-candidate",
            candidate_callsign="CANDIDATE",
            candidate_points=candidate_points,
            candidate_eobt=t_base,
            candidate_eta=t_eta,
            db=self.db,
            log_to_db=False,
            aircraft_type="A320"
        )
        # Should be NO airborne conflict because vertical separation is 2,000 ft (>= 1,000 ft)
        airborne_conflicts = [c for c in outcome.conflicts if c.conflict_type != "AIRPORT_SLOT_CONFLICT"]
        self.assertEqual(len(airborne_conflicts), 0, f"Unexpected conflict: {[c.description for c in airborne_conflicts]}")

        # Flight 3 at identical coordinates and time, but FL305 (30,500 ft -> delta 500 ft < 1,000 ft)
        plan3 = FlightPlanModel(
            gufi="test-gufi-loss-vert-sep",
            callsign="TEST03",
            status="FILED",
            departure_icao="EGLL",
            departure_runway="27R",
            arrival_icao="EIDW",
            arrival_runway="28L",
            eobt=t_base + timedelta(minutes=10), # Offset departure so departure slot doesn't trigger
            eta=t_eta,
            aircraft_type="A320",
            cruising_level="F305",
            route_string="EGLL LIPGO EIDW",
            fixm_json="{}",
            fixm_xml="<xml/>"
        )
        self.db.add(plan3)
        pt3 = TrajectoryPointModel(
            gufi="test-gufi-loss-vert-sep",
            point_index=1,
            point_type="WAYPOINT",
            identifier="LIPGO",
            latitude=53.0,
            longitude=-4.0,
            altitude_feet=30500,
            flight_level=305,
            timestamp=t_overflight
        )
        self.db.add(pt3)
        self.db.commit()

        outcome2 = deconflict_trajectory(
            candidate_gufi="test-candidate",
            candidate_callsign="CANDIDATE",
            candidate_points=candidate_points,
            candidate_eobt=t_base,
            candidate_eta=t_eta,
            db=self.db,
            log_to_db=False,
            aircraft_type="A320"
        )
        conflicts3 = [c for c in outcome2.conflicts if c.conflicting_callsign == "TEST03"]
        self.assertGreater(len(conflicts3), 0, "Expected airborne conflict with TEST03 due to < 1,000 ft vertical separation!")

        # Clean up
        self.db.query(TrajectoryPointModel).filter(TrajectoryPointModel.gufi.in_(["test-gufi-vert-sep", "test-gufi-loss-vert-sep"])).delete()
        self.db.query(FlightPlanModel).filter(FlightPlanModel.gufi.in_(["test-gufi-vert-sep", "test-gufi-loss-vert-sep"])).delete()
        self.db.commit()

    def test_airport_slots_generation(self):
        """Verifies 5-minute runway slot schedule generation and status."""
        target_date = datetime(2026, 6, 1).date()
        res = get_airport_slots("EGLL", target_date, "DEPARTURE", db=self.db, candidate_ac_type="A320")
        slots = res["slots"]
        
        self.assertGreater(len(slots), 200, "Should generate 200+ 5-minute slots for operational day")
        first_slot = slots[0]
        self.assertIn("slot_id", first_slot)
        self.assertIn("status", first_slot)
        self.assertIn(first_slot["status"], ["AVAILABLE", "OCCUPIED"])

    def test_find_next_available_slot(self):
        """Verifies finding the next available slot given a desired departure time."""
        desired_time = datetime(2026, 6, 1, 10, 2, 0, tzinfo=timezone.utc)
        next_slot = find_next_available_slot("EGLL", desired_time, "DEPARTURE", db=self.db, candidate_ac_type="A320")
        self.assertIsNotNone(next_slot)
        self.assertEqual(next_slot.status, "AVAILABLE")


if __name__ == "__main__":
    unittest.main()
