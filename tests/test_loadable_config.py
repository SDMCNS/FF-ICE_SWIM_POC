"""
Unit tests for the Loadable JSON Configuration System.
Verifies:
1. Loading base configurations from config/*.json
2. Dynamic lookup of aircraft performance, wake turbulence matrices, and airway corridors.
3. User custom override merging and hot-reloading.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from ff_ice_server.config_loader import (
    get_aircraft_database,
    get_aircraft_perf,
    get_aircraft_wake_category,
    get_departure_wake_interval,
    get_approach_wake_separation,
    get_waypoint_alternates,
    get_airway_routes,
    reload_configuration,
    save_custom_override
)


class TestLoadableConfig(unittest.TestCase):

    def setUp(self):
        reload_configuration()

    def test_01_aircraft_database_loaded_from_json(self):
        db = get_aircraft_database()
        self.assertIn("A320", db)
        self.assertIn("B738", db)
        self.assertIn("B77W", db)
        self.assertIn("B789", db)
        self.assertIn("A333", db)
        self.assertIn("C172", db)
        self.assertIn("PC12", db)

        b789 = get_aircraft_perf("B789")
        self.assertEqual(b789["ceiling"], 430)
        self.assertEqual(b789["cruiseTasKnots"], 490)
        self.assertEqual(get_aircraft_wake_category("B789"), "H")

    def test_02_wake_turbulence_rules_loaded(self):
        self.assertEqual(get_departure_wake_interval("H", "L"), 180)
        self.assertEqual(get_departure_wake_interval("H", "M"), 120)
        self.assertEqual(get_departure_wake_interval("M", "M"), 90)

        self.assertEqual(get_approach_wake_separation("H", "L"), 6.0)
        self.assertEqual(get_approach_wake_separation("H", "M"), 5.0)
        self.assertEqual(get_approach_wake_separation("M", "M"), 3.0)

    def test_03_airway_corridors_and_alternates_loaded(self):
        airways = get_airway_routes()
        airway_ids = [a["airwayId"] for a in airways]
        self.assertIn("L18", airway_ids)
        self.assertIn("L149", airway_ids)
        self.assertIn("L975", airway_ids)

        lipgo_alts = get_waypoint_alternates("LIPGO")
        self.assertIn("OLAPO", lipgo_alts)
        self.assertIn("SUROX", lipgo_alts)

    def test_04_custom_overrides_merging(self):
        # Inject custom aircraft profile
        custom_test_ac = {
            "icaoType": "TEST_JET",
            "manufacturer": "TestAero",
            "model": "Custom-X",
            "wake": "M",
            "ceiling": 450,
            "typicalFl": 410,
            "cruiseTasKnots": 510,
            "cruiseTas": 510,
            "climbRate": 3000,
            "climbSpeed": 350,
            "descentRate": 2500,
            "descentSpeed": 320,
            "descentGrad": 318,
            "defaultEquipment": "SDFGIRW/LB1"
        }
        save_custom_override("aircraft", "TEST_JET", custom_test_ac)

        loaded_test = get_aircraft_perf("TEST_JET")
        self.assertEqual(loaded_test["manufacturer"], "TestAero")
        self.assertEqual(loaded_test["cruiseTasKnots"], 510)
        self.assertEqual(loaded_test["ceiling"], 450)

        # Clean up test override
        save_custom_override("aircraft", "TEST_JET", {})
        reload_configuration()


if __name__ == "__main__":
    unittest.main()

