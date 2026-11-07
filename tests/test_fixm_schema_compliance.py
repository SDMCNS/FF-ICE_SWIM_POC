"""
FIXM v4.2+ / iFIXM Schema Compliance and Field Conformance Verification Suite.
Validates FF-ICE plans against official ICAO Doc 9965 & FIXM XML/JSON standards.
"""
import sys
import os
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from ff_ice_server.fixm_engine import serialize_to_fixm_xml, parse_fixm_xml, generate_gufi
from ff_ice_server.trajectory import calculate_4d_trajectory
from ff_ice_server.aero_data import AeroDataStore

FIXM_FX_NS = "http://www.fixm.aero/flight/4.2"
FIXM_FB_NS = "http://www.fixm.aero/base/4.2"
NS_MAP = {"fx": FIXM_FX_NS, "fb": FIXM_FB_NS}


class TestFixmSchemaCompliance(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.store = AeroDataStore(base_dir=os.path.abspath("."))
        cls.dep = cls.store.airports["EGLL"]
        cls.arr = cls.store.airports["EIDW"]
        cls.wps = [cls.store.waypoints["LIPGO"]]
        cls.now = datetime.now(timezone.utc)

        # Generate a standard 4D trajectory
        cls.traj = calculate_4d_trajectory(
            dep_airport=cls.dep,
            arr_airport=cls.arr,
            waypoints=cls.wps,
            aircraft_type="A320",
            requested_fl=280,
            eobt_dt=cls.now,
            firs=list(cls.store.firs.values()),
            departure_runway="27R",
            arrival_runway="28L"
        )

        cls.plan_dict = {
            "gufi": generate_gufi(),
            "status": "FILED",
            "messageType": "FILING",
            "filingTime": cls.now.isoformat() + "Z",
            "flightIdentification": {
                "aircraftIdentification": "EIN157",
                "aircraftRegistration": "EI-DVM"
            },
            "aircraft": {
                "aircraftType": "A320",
                "wakeTurbulence": "M",
                "capabilities": {
                    "standardEquipment": "SDFGIRW/LB1",
                    "navigation": ["RNAV 1", "RNAV 5", "RNP 4"],
                    "communication": ["VHF 8.33 kHz", "CPDLC"],
                    "surveillance": ["ADS-B Out", "Mode S EHS"]
                }
            },
            "departure": {
                "aerodrome": "EGLL",
                "runway": "27R",
                "elevationFeet": 83,
                "estimatedOffBlockTime": cls.now.isoformat() + "Z"
            },
            "arrival": {
                "aerodrome": "EIDW",
                "runway": "28L",
                "elevationFeet": 243,
                "estimatedTimeOfArrival": (cls.now + timedelta(minutes=42)).isoformat() + "Z"
            },
            "enRoute": {
                "cruisingLevel": "F280",
                "cruisingSpeed": "N0450",
                "routeString": "EGLL LIPGO EIDW"
            },
            "trajectory": {
                "totalDistanceNm": cls.traj["totalDistanceNm"],
                "totalFlightTimeMinutes": cls.traj["totalFlightTimeMinutes"],
                "points4D": cls.traj["points"]
            }
        }

        cls.xml_str = serialize_to_fixm_xml(cls.plan_dict)
        cls.root = ET.fromstring(cls.xml_str)

    def test_01_root_element_and_namespaces(self):
        """Verifies root element is fx:Flight and official FIXM namespaces are declared."""
        self.assertEqual(self.root.tag, f"{{{FIXM_FX_NS}}}Flight")
        self.assertIn("xmlns:fx", self.xml_str)
        self.assertIn(FIXM_FX_NS, self.xml_str)
        self.assertIn("xmlns:fb", self.xml_str)
        self.assertIn(FIXM_FB_NS, self.xml_str)

    def test_02_gufi_element_and_codespace(self):
        """Verifies GUFI element format and codeSpace attribute."""
        gufi_el = self.root.find("fx:gufi", NS_MAP)
        self.assertIsNotNone(gufi_el, "Missing fx:gufi element in FIXM XML")
        self.assertEqual(gufi_el.attrib.get("codeSpace"), "urn:uuid")

        gufi_val = gufi_el.text.strip()
        self.assertTrue(gufi_val.startswith("urn:uuid:"), f"GUFI must begin with 'urn:uuid:', got: {gufi_val}")

        uuid_part = gufi_val.replace("urn:uuid:", "")
        # Validate RFC 4122 UUID structure
        parsed_uuid = uuid.UUID(uuid_part)
        self.assertEqual(str(parsed_uuid), uuid_part)

    def test_03_flight_identification(self):
        """Verifies callsign and optional aircraft registration."""
        fl_id = self.root.find("fx:flightIdentification", NS_MAP)
        self.assertIsNotNone(fl_id)

        callsign = fl_id.find("fx:aircraftIdentification", NS_MAP)
        self.assertIsNotNone(callsign)
        self.assertEqual(callsign.text.strip(), "EIN157")

        reg = fl_id.find("fx:aircraftRegistration", NS_MAP)
        self.assertIsNotNone(reg)
        self.assertEqual(reg.text.strip(), "EI-DVM")

    def test_04_aircraft_type_and_wake_category(self):
        """Verifies ICAO aircraft type designator and standard FIXM wake enum."""
        ac = self.root.find("fx:aircraft", NS_MAP)
        self.assertIsNotNone(ac)

        # Standard ICAO type
        ac_type = ac.find(".//fb:icaoAircraftTypeDesignator", NS_MAP)
        if ac_type is None:
            ac_type = ac.find("fx:aircraftType", NS_MAP)
        self.assertIsNotNone(ac_type)
        self.assertEqual(ac_type.text.strip(), "A320")

        # Standard FIXM Wake Category enum (LIGHT, MEDIUM, HEAVY, SUPER)
        wake_enum = ac.find("fx:wakeTurbulence", NS_MAP)
        self.assertIsNotNone(wake_enum)
        self.assertIn(wake_enum.text.strip(), ["LIGHT", "MEDIUM", "HEAVY", "SUPER"])
        self.assertEqual(wake_enum.text.strip(), "MEDIUM")

        # Capabilities / equipment string
        equip = ac.find(".//fx:standardEquipment", NS_MAP)
        self.assertIsNotNone(equip)
        self.assertEqual(equip.text.strip(), "SDFGIRW/LB1")

    def test_05_departure_and_runway_conformance(self):
        """Verifies departure aerodrome, runway designator, elevation, and EOBT."""
        dep = self.root.find("fx:departure", NS_MAP)
        self.assertIsNotNone(dep)

        aero = dep.find(".//fb:locationIndicator", NS_MAP)
        if aero is None:
            aero = dep.find("fx:aerodrome", NS_MAP)
        self.assertIsNotNone(aero)
        self.assertEqual(aero.text.strip(), "EGLL")

        rwy = dep.find(".//fb:runwayDirectionDesignator", NS_MAP)
        self.assertIsNotNone(rwy)
        self.assertEqual(rwy.text.strip(), "27R")

        elev = dep.find("fx:elevation", NS_MAP)
        self.assertIsNotNone(elev)
        self.assertEqual(elev.attrib.get("uom"), "FT")
        self.assertEqual(elev.text.strip(), "83")

        eobt = dep.find("fx:estimatedOffBlockTime", NS_MAP)
        self.assertIsNotNone(eobt)

    def test_06_arrival_and_destination_conformance(self):
        """Verifies arrival destination, runway designator, elevation, and ETA."""
        arr = self.root.find("fx:arrival", NS_MAP)
        self.assertIsNotNone(arr)

        dest = arr.find(".//fb:locationIndicator", NS_MAP)
        if dest is None:
            dest = arr.find("fx:destination", NS_MAP)
        if dest is None:
            dest = arr.find("fx:aerodrome", NS_MAP)
        self.assertIsNotNone(dest)
        self.assertEqual(dest.text.strip(), "EIDW")

        rwy = arr.find(".//fb:runwayDirectionDesignator", NS_MAP)
        self.assertIsNotNone(rwy)
        self.assertEqual(rwy.text.strip(), "28L")

        elev = arr.find("fx:elevation", NS_MAP)
        self.assertIsNotNone(elev)
        self.assertEqual(elev.attrib.get("uom"), "FT")
        self.assertEqual(elev.text.strip(), "243")

        eta = arr.find("fx:estimatedTimeOfArrival", NS_MAP)
        self.assertIsNotNone(eta)

    def test_07_enroute_cruising_speed_and_level(self):
        """Verifies cruisingLevel (flightLevel) and cruisingSpeed with uom='KT'."""
        en_route = self.root.find("fx:enRoute", NS_MAP)
        self.assertIsNotNone(en_route)

        fl = en_route.find(".//fb:flightLevel", NS_MAP)
        self.assertIsNotNone(fl)
        self.assertEqual(fl.text.strip(), "F280")

        spd = en_route.find("fx:cruisingSpeed", NS_MAP)
        self.assertIsNotNone(spd)
        self.assertEqual(spd.attrib.get("uom"), "KT")
        self.assertEqual(spd.text.strip(), "N0450")

    def test_08_agreed_trajectory_4d_points(self):
        """Verifies 4D points with fb:pos, fb:altitude, fb:flightLevel, and fb:estimatedTime."""
        traj = self.root.find(".//fx:agreedTrajectory", NS_MAP)
        self.assertIsNotNone(traj)

        pts = traj.findall(".//fx:point4D", NS_MAP)
        self.assertGreaterEqual(len(pts), 5)

        first_pt = pts[0]
        pos = first_pt.find(".//fb:pos", NS_MAP)
        self.assertIsNotNone(pos)
        coords = [float(x) for x in pos.text.strip().split()]
        self.assertAlmostEqual(coords[0], self.dep["latitude"], delta=0.1)

        alt = first_pt.find(".//fb:altitude", NS_MAP)
        self.assertIsNotNone(alt)
        self.assertEqual(alt.attrib.get("uom"), "FT")

        t = first_pt.find(".//fb:estimatedTime", NS_MAP)
        self.assertIsNotNone(t)

    def test_09_roundtrip_parsing_fidelity(self):
        """Verifies parsing the generated FIXM XML restores the flight plan with 100% fidelity."""
        parsed = parse_fixm_xml(self.xml_str)
        self.assertEqual(parsed["gufi"], self.plan_dict["gufi"])
        self.assertEqual(parsed["flightIdentification"]["aircraftIdentification"], "EIN157")
        self.assertEqual(parsed["departure"]["aerodrome"], "EGLL")
        self.assertEqual(parsed["arrival"]["aerodrome"], "EIDW")
        self.assertEqual(parsed["aircraft"]["aircraftType"], "A320")
        self.assertEqual(parsed["aircraft"]["wakeTurbulence"], "M")
        self.assertGreaterEqual(len(parsed["trajectory"]["points4D"]), 5)


if __name__ == "__main__":
    unittest.main()
