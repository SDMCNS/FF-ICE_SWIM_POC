"""
Unit Tests for Aeronautical Waypoint Graph, A* Shortest Path, and K-Alternative Routing.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("."))
from ff_ice_server.aero_data import AeroDataStore
from ff_ice_server.airspace_graph import AirspaceGraph, get_airspace_graph

class TestAirspaceGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = AeroDataStore(base_dir=os.path.abspath("."))
        cls.graph = get_airspace_graph()

    def test_01_graph_construction(self):
        print("\n--- Test 1: Aeronautical Graph Construction ---")
        self.assertGreaterEqual(len(self.graph.nodes), 1050)
        self.assertGreaterEqual(len(self.graph.adj), 1050)
        total_edges = sum(len(v) for v in self.graph.adj.values()) // 2
        self.assertGreater(total_edges, 3000)
        print(f"[PASS] Airspace Graph loaded: {len(self.graph.nodes)} nodes, {total_edges} bidirectional flight edges.")

    def test_02_dynamic_waypoint_alternates(self):
        print("\n--- Test 2: Dynamic Waypoint Alternates ---")
        lipgo_alts = self.graph.get_waypoint_alternates("LIPGO", limit=4)
        self.assertGreaterEqual(len(lipgo_alts), 1)
        self.assertNotIn("LIPGO", lipgo_alts)
        print(f"[PASS] Dynamic alternates for LIPGO: {lipgo_alts}")

        surox_alts = self.graph.get_waypoint_alternates("SUROX", limit=4)
        self.assertGreaterEqual(len(surox_alts), 1)
        self.assertNotIn("SUROX", surox_alts)
        print(f"[PASS] Dynamic alternates for SUROX: {surox_alts}")

    def test_03_astar_shortest_path(self):
        print("\n--- Test 3: A* Shortest Path Routing ---")
        path, dist = self.graph.shortest_path("LUXTO", "LIPGO")
        self.assertIsNotNone(path)
        self.assertEqual(path[0], "LUXTO")
        self.assertEqual(path[-1], "LIPGO")
        self.assertGreater(dist, 100.0)
        self.assertLess(dist, 300.0)
        print(f"[PASS] A* Shortest Path LUXTO -> LIPGO: {path} ({dist:.1f} NM)")

    def test_04_avoidance_routing(self):
        print("\n--- Test 4: Conflict Avoidance Routing ---")
        # Direct shortest path
        path1, dist1 = self.graph.shortest_path("LUXTO", "LIPGO")
        self.assertIsNotNone(path1)

        # Avoid a middle waypoint in path1
        avoid_target = path1[len(path1) // 2]
        path2, dist2 = self.graph.shortest_path("LUXTO", "LIPGO", avoid={avoid_target})
        self.assertIsNotNone(path2)
        self.assertNotIn(avoid_target, path2)
        self.assertGreaterEqual(dist2, dist1)
        print(f"[PASS] Avoidance routing successfully routed around {avoid_target}:")
        print(f"       Direct: {path1} ({dist1:.1f} NM)")
        print(f"       Bypass: {path2} ({dist2:.1f} NM, delta +{dist2 - dist1:.1f} NM)")

    def test_05_k_alternative_paths(self):
        print("\n--- Test 5: K-Alternative Paths ---")
        alts = self.graph.find_alternative_paths("LUXTO", "LIPGO", k=3)
        self.assertGreaterEqual(len(alts), 2)
        print(f"[PASS] Generated {len(alts)} alternative corridors:")
        for a in alts:
            print(f"       Rank {a['rank']}: {a['waypoints']} -> {a['totalDistanceNm']} NM (+{a['deltaDistanceNm']} NM) - {a['description']}")

    def test_06_lateral_bypass_for_conflict(self):
        print("\n--- Test 6: Lateral Bypass Generation for Conflict Fix ---")
        route = ["LUXTO", "PEPZE", "SUROX", "LIPGO"]
        bypasses = self.graph.find_lateral_bypass(route, "SUROX", limit=2)
        self.assertGreater(len(bypasses), 0)
        for b in bypasses:
            self.assertNotEqual(b["newWaypoint"], "SUROX")
            print(f"[PASS] Bypass generated for SUROX: Detour via {b['newWaypoint']} ({b['description']})")

if __name__ == "__main__":
    unittest.main()

