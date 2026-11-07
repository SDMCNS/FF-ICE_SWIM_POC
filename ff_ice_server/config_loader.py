"""
Dynamic Loadable JSON Configuration Engine for FF-ICE & SWIM Services.
Loads and hot-reloads aircraft performance profiles, wake turbulence matrices,
airway corridors, and custom user overrides from JSON files.
"""
import os
import re
import json
import threading
from typing import Dict, Any, List, Optional, Tuple

_LOCK = threading.RLock()

# Default fallback config paths
CONFIG_DIR = os.environ.get(
    "FF_ICE_CONFIG_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config"))
)

AIRCRAFT_CONFIG_FILE = os.path.join(CONFIG_DIR, "aircraft_performance.json")
WAKE_CONFIG_FILE = os.path.join(CONFIG_DIR, "wake_turbulence_rules.json")
CORRIDORS_CONFIG_FILE = os.path.join(CONFIG_DIR, "airspace_corridors.json")
AIRPORT_OPS_CONFIG_FILE = os.path.join(CONFIG_DIR, "airport_operations.json")
OVERRIDES_CONFIG_FILE = os.path.join(CONFIG_DIR, "custom_overrides.json")

# In-memory cached configs
_AIRCRAFT_PERF: Dict[str, Dict[str, Any]] = {}
_WAKE_DEPARTURE_SEC: Dict[Tuple[str, str], int] = {}
_WAKE_APPROACH_NM: Dict[Tuple[str, str], float] = {}
_WAYPOINT_ALTERNATES: Dict[str, List[str]] = {}
_AIRWAYS: List[Dict[str, Any]] = []
_AIRPORT_OPS: Dict[str, Any] = {}
_CONFIG_METADATA: Dict[str, Any] = {}

def _load_json_file(file_path: str) -> Dict[str, Any]:
    if not os.path.isfile(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Error reading JSON configuration from {file_path}: {e}")
        return {}

def reload_configuration() -> Dict[str, Any]:
    """
    Loads all JSON configuration files from disk, merges user custom overrides,
    and updates cached in-memory structures thread-safely.
    """
    global _AIRCRAFT_PERF, _WAKE_DEPARTURE_SEC, _WAKE_APPROACH_NM, _WAYPOINT_ALTERNATES, _AIRWAYS, _AIRPORT_OPS, _CONFIG_METADATA

    with _LOCK:
        # 1. Aircraft Performance
        ac_data = _load_json_file(AIRCRAFT_CONFIG_FILE)
        ac_map = ac_data.get("aircraft", {})

        # 2. Wake Turbulence Rules
        wake_data = _load_json_file(WAKE_CONFIG_FILE)
        dep_map_raw = wake_data.get("departureWakeIntervalsSec", {})
        app_map_raw = wake_data.get("approachWakeSeparationNm", {})

        # Parse pairs e.g. "H_M" -> ("H", "M")
        new_dep_sec: Dict[Tuple[str, str], int] = {}
        for k, v in dep_map_raw.items():
            parts = k.split("_")
            if len(parts) == 2:
                new_dep_sec[(parts[0].upper(), parts[1].upper())] = int(v)

        new_app_nm: Dict[Tuple[str, str], float] = {}
        for k, v in app_map_raw.items():
            parts = k.split("_")
            if len(parts) == 2:
                new_app_nm[(parts[0].upper(), parts[1].upper())] = float(v)

        # 3. Airspace Corridors & Alternates
        corridor_data = _load_json_file(CORRIDORS_CONFIG_FILE)
        new_airways = corridor_data.get("airways", [])
        new_alternates = corridor_data.get("waypointAlternates", {})

        # 4. Airport Operations & Runway Configurations
        airport_ops_data = _load_json_file(AIRPORT_OPS_CONFIG_FILE)
        new_airport_ops = airport_ops_data.get("airports", {})
        default_ops = airport_ops_data.get("defaultOperations", {})

        # 5. User Custom Overrides
        overrides = _load_json_file(OVERRIDES_CONFIG_FILE)
        custom_ac = overrides.get("aircraft", {})
        for ac_code, ac_fields in custom_ac.items():
            code_clean = ac_code.upper()
            if code_clean in ac_map:
                ac_map[code_clean].update(ac_fields)
            else:
                ac_map[code_clean] = ac_fields

        custom_dep = overrides.get("departureWakeIntervalsSec", {})
        for k, v in custom_dep.items():
            parts = k.split("_")
            if len(parts) == 2:
                new_dep_sec[(parts[0].upper(), parts[1].upper())] = int(v)

        custom_app = overrides.get("approachWakeSeparationNm", {})
        for k, v in custom_app.items():
            parts = k.split("_")
            if len(parts) == 2:
                new_app_nm[(parts[0].upper(), parts[1].upper())] = float(v)

        custom_alts = overrides.get("waypointAlternates", {})
        for fix, alts in custom_alts.items():
            new_alternates[fix.upper()] = alts

        custom_ops = overrides.get("airports", {})
        for icao, ops_data in custom_ops.items():
            code_clean = icao.upper()
            if code_clean in new_airport_ops:
                new_airport_ops[code_clean].update(ops_data)
            else:
                new_airport_ops[code_clean] = ops_data

        # Fallback defaults if files missing
        if not ac_map:
            ac_map = {
                "A320": {
                    "icaoType": "A320", "manufacturer": "Airbus", "model": "A320",
                    "wake": "M", "ceiling": 390, "typicalFl": 340, "cruiseTas": 450,
                    "climbRate": 2200, "climbSpeed": 320, "descentRate": 2000,
                    "descentSpeed": 290, "descentGrad": 318, "defaultEquipment": "SDFGIRW/LB1"
                }
            }

        # Normalize and synchronize both camelCase and short/legacy property aliases
        for ac_code, profile in ac_map.items():
            profile["icaoType"] = profile.get("icaoType", ac_code)
            ceiling = int(profile.get("serviceCeilingFl", profile.get("ceiling", 390)))
            profile["serviceCeilingFl"] = ceiling
            profile["ceiling"] = ceiling
            climb = int(profile.get("averageClimbRateFpm", profile.get("climbRate", 2200)))
            profile["averageClimbRateFpm"] = climb
            profile["climbRate"] = climb
            tas = int(profile.get("cruiseTasKnots", profile.get("cruiseTas", 450)))
            profile["cruiseTasKnots"] = tas
            profile["cruiseTas"] = tas
            descent = int(profile.get("averageDescentRateFpm", profile.get("descentRate", 2000)))
            profile["averageDescentRateFpm"] = descent
            profile["descentRate"] = descent
            typical = int(profile.get("typicalCruiseFl", profile.get("typicalFl", 340)))
            profile["typicalCruiseFl"] = typical
            profile["typicalFl"] = typical
            equip = profile.get("defaultEquipment", profile.get("equipment", "SDFGIRW/LB1"))
            profile["defaultEquipment"] = equip
            profile["equipment"] = equip
            wake = profile.get("wake", "M").upper()
            profile["wake"] = wake
            if "wakeTurbulenceCategory" not in profile:
                wake_map = {"L": "LIGHT", "M": "MEDIUM", "H": "HEAVY", "J": "SUPER"}
                profile["wakeTurbulenceCategory"] = wake_map.get(wake, "MEDIUM")

        _AIRCRAFT_PERF = ac_map
        _WAKE_DEPARTURE_SEC = new_dep_sec
        _WAKE_APPROACH_NM = new_app_nm
        _WAYPOINT_ALTERNATES = new_alternates
        _AIRWAYS = new_airways
        _AIRPORT_OPS = {
            "default": default_ops,
            "airports": new_airport_ops
        }

        _CONFIG_METADATA = {
            "status": "LOADED",
            "configDir": CONFIG_DIR,
            "aircraftCount": len(_AIRCRAFT_PERF),
            "wakeDepartureRulesCount": len(_WAKE_DEPARTURE_SEC),
            "wakeApproachRulesCount": len(_WAKE_APPROACH_NM),
            "waypointAlternatesCount": len(_WAYPOINT_ALTERNATES),
            "airwaysCount": len(_AIRWAYS),
            "airportOperationsCount": len(new_airport_ops)
        }

    return _CONFIG_METADATA

# Initial load on module import
reload_configuration()

def get_aircraft_database() -> Dict[str, Dict[str, Any]]:
    """Returns all loaded aircraft performance profiles."""
    with _LOCK:
        return dict(_AIRCRAFT_PERF)

def get_aircraft_perf(ac_type: str) -> Dict[str, Any]:
    """Retrieves aircraft performance profile with graceful fallback to A320."""
    with _LOCK:
        clean = (ac_type or "A320").strip().upper()
        return _AIRCRAFT_PERF.get(clean, _AIRCRAFT_PERF.get("A320", {}))

def get_aircraft_wake_category(ac_type: str) -> str:
    """Returns 'L', 'M', 'H', or 'J' based on configured aircraft performance."""
    perf = get_aircraft_perf(ac_type)
    wake = perf.get("wake") or perf.get("wakeTurbulenceCategory", "M")
    if wake == "LIGHT": return "L"
    if wake == "MEDIUM": return "M"
    if wake == "HEAVY": return "H"
    if wake == "SUPER": return "J"
    return str(wake).upper()[:1]

def get_departure_wake_interval(lead_wake: str, trail_wake: str) -> int:
    """Returns runway departure separation interval in seconds from loaded rules."""
    with _LOCK:
        pair = (lead_wake.upper(), trail_wake.upper())
        return _WAKE_DEPARTURE_SEC.get(pair, 90)

def get_approach_wake_separation(lead_wake: str, trail_wake: str) -> float:
    """Returns approach radar separation in NM from loaded rules."""
    with _LOCK:
        pair = (lead_wake.upper(), trail_wake.upper())
        return _WAKE_APPROACH_NM.get(pair, 3.0)

def get_waypoint_alternates(fix_name: str) -> List[str]:
    """Returns list of lateral corridor bypass waypoints from loaded rules."""
    with _LOCK:
        clean = fix_name.strip().upper()
        return list(_WAYPOINT_ALTERNATES.get(clean, []))

def get_airway_routes() -> List[Dict[str, Any]]:
    """Returns list of ATS airway routes loaded from JSON."""
    with _LOCK:
        return list(_AIRWAYS)

def get_runway_reciprocal(designator: str) -> str:
    """
    Computes reciprocal runway end designator (e.g. 27L -> 09R, 09L -> 27R, 04 -> 22, 36C -> 18C).
    """
    if not designator: return ""
    des = str(designator).strip().upper()
    m = re.match(r"^(\d{1,2})([LCR])?$", des)
    if not m: return des
    num = int(m.group(1))
    suffix = m.group(2) or ""
    recip_num = (num + 18) % 36
    if recip_num == 0: recip_num = 36
    recip_suffix = "R" if suffix == "L" else ("L" if suffix == "R" else suffix)
    return f"{recip_num:02d}{recip_suffix}"

def get_canonical_strip_id(runway_a: str, runway_b: Optional[str] = None) -> str:
    """
    Returns sorted, canonical physical concrete strip identifier (e.g. '09L/27R').
    """
    if not runway_b:
        runway_b = get_runway_reciprocal(runway_a)
    ends = sorted([runway_a.strip().upper(), runway_b.strip().upper()])
    return f"{ends[0]}/{ends[1]}"

def synthesize_airport_operations(icao: str, runways: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Dynamically synthesizes operational mode, physical concrete strips,
    and segregated arrival/departure roles for an aerodrome based on its actual AIP runways.
    Ensures that when parallel runways are present, departures and arrivals do not share
    the same strip of concrete.
    """
    clean_icao = icao.strip().upper()
    default_cfg = _AIRPORT_OPS.get("default", {})
    if not runways:
        return {
            "icao": clean_icao,
            "mode": default_cfg.get("defaultMode", "MIXED_MODE_SINGLE"),
            "physicalStrips": [],
            "taxiOutMinutes": default_cfg.get("defaultTaxiOutMinutes", 10),
            "taxiInMinutes": default_cfg.get("defaultTaxiInMinutes", 6),
            "mixedModeOccupancyBufferSec": default_cfg.get("mixedModeOccupancyBufferSec", 75)
        }

    # Group runway designators into reciprocal physical strips
    des_list = [r["designator"].strip().upper() for r in runways if r.get("designator")]
    strips_map: Dict[str, List[str]] = {}
    for des in des_list:
        canon = get_canonical_strip_id(des)
        if canon not in strips_map:
            strips_map[canon] = []
        if des not in strips_map[canon]:
            strips_map[canon].append(des)

    strip_ids = sorted(strips_map.keys())
    num_strips = len(strip_ids)

    # Detect if multiple strips are parallel (headings within 10 degrees or L/C/R suffixes)
    is_parallel = False
    if num_strips >= 2:
        headings = []
        for s in strip_ids:
            m = re.match(r"^(\d{2})", s)
            if m: headings.append(int(m.group(1)))
        if len(headings) >= 2 and max(headings) - min(headings) <= 1:
            is_parallel = True

    if num_strips <= 1 or not is_parallel:
        mode = "MIXED_MODE_SINGLE"
    elif num_strips == 2:
        mode = "PARALLEL_SEGREGATED"
    else:
        mode = "MULTIPLE_PARALLEL"

    # Build physical strip configurations with segregated roles
    physical_strips = []
    west_deps, west_arrs = [], []
    east_deps, east_arrs = [], []

    for idx, sid in enumerate(strip_ids):
        ends = sid.split("/")
        end_a = ends[0] # e.g. 09L
        end_b = ends[1] if len(ends) > 1 else get_runway_reciprocal(end_a) # e.g. 27R

        if mode in ["PARALLEL_SEGREGATED", "MULTIPLE_PARALLEL"]:
            # Segregated parallel operations: one runway handles departures, other handles arrivals!
            if idx % 2 == 0:
                west_arrs.append(end_b)
                east_arrs.append(end_a)
                role = {"WEST": "ARRIVAL", "EAST": "ARRIVAL"}
                desc = f"Physical concrete strip {sid}: Exclusively dedicated to ARRIVALS."
            else:
                west_deps.append(end_b)
                east_deps.append(end_a)
                role = {"WEST": "DEPARTURE", "EAST": "DEPARTURE"}
                desc = f"Physical concrete strip {sid}: Exclusively dedicated to DEPARTURES."
        else:
            west_deps.append(end_b)
            west_arrs.append(end_b)
            east_deps.append(end_a)
            east_arrs.append(end_a)
            role = {"WEST": "MIXED", "EAST": "MIXED"}
            desc = f"Single physical concrete strip {sid}: Interleaves arrivals and departures."

        physical_strips.append({
            "stripId": sid,
            "runwayEnds": [end_a, end_b],
            "segregatedRole": role,
            "description": desc
        })

    return {
        "icao": clean_icao,
        "mode": mode,
        "physicalStrips": physical_strips,
        "westOperations": {
            "departureRunways": west_deps or [strip_ids[0].split("/")[0]],
            "arrivalRunways": west_arrs or [strip_ids[0].split("/")[0]]
        },
        "eastOperations": {
            "departureRunways": east_deps or [strip_ids[0].split("/")[-1]],
            "arrivalRunways": east_arrs or [strip_ids[0].split("/")[-1]]
        },
        "taxiOutMinutes": 16 if mode == "MULTIPLE_PARALLEL" else (12 if mode == "PARALLEL_SEGREGATED" else 10),
        "taxiInMinutes": 9 if mode == "MULTIPLE_PARALLEL" else (7 if mode == "PARALLEL_SEGREGATED" else 6),
        "mixedModeOccupancyBufferSec": 60 if is_parallel else 75
    }

def get_runway_physical_strip_id(icao: str, runway_designator: str) -> str:
    """
    Finds or derives the physical concrete strip ID for a given runway designator at an aerodrome.
    """
    if not runway_designator: return ""
    des_clean = str(runway_designator).strip().upper()
    ops = get_airport_operations(icao)
    strips = ops.get("physicalStrips", [])
    for strip in strips:
        ends = [e.upper() for e in strip.get("runwayEnds", [])]
        if des_clean in ends or strip.get("stripId") == des_clean:
            return strip.get("stripId", des_clean)
    return get_canonical_strip_id(des_clean)

def get_airport_physical_strips(icao: str) -> List[Dict[str, Any]]:
    """
    Returns list of physical concrete strips for an aerodrome.
    """
    ops = get_airport_operations(icao)
    return list(ops.get("physicalStrips", []))

def get_airport_operations(icao: Optional[str] = None) -> Dict[str, Any]:
    """Returns operational and runway mode configuration for an aerodrome, or all if icao is None."""
    with _LOCK:
        airports = _AIRPORT_OPS.get("airports", {})
        default_cfg = _AIRPORT_OPS.get("default", {})
        if not icao:
            return airports

        clean = icao.strip().upper()
        if clean in airports:
            merged = dict(default_cfg)
            merged.update(airports[clean])
            return merged

        # Check if known in aerodrome data store to auto-synthesize
        try:
            from .aero_data import AeroDataStore
            # Check cached or lazy store
            store = getattr(get_airport_operations, "_store", None)
            if store is None:
                store = AeroDataStore()
                setattr(get_airport_operations, "_store", store)
            if clean in store.airports:
                synth = synthesize_airport_operations(clean, store.airports[clean].get("runways", []))
                airports[clean] = synth
                merged = dict(default_cfg)
                merged.update(synth)
                return merged
        except Exception:
            pass

        return {
            "icao": clean,
            "mode": default_cfg.get("defaultMode", "MIXED_MODE_SINGLE"),
            "physicalStrips": [],
            "taxiOutMinutes": default_cfg.get("defaultTaxiOutMinutes", 10),
            "taxiInMinutes": default_cfg.get("defaultTaxiInMinutes", 6),
            "mixedModeOccupancyBufferSec": default_cfg.get("mixedModeOccupancyBufferSec", 75)
        }

def get_airport_runway_mode(icao: str) -> str:
    """Returns 'PARALLEL_SEGREGATED', 'MIXED_MODE_SINGLE', or 'MULTIPLE_PARALLEL'."""
    return get_airport_operations(icao).get("mode", "MIXED_MODE_SINGLE")

def is_parallel_segregated_airport(icao: str) -> bool:
    """Returns True if the airport operates parallel segregated runway operations."""
    return get_airport_runway_mode(icao) in ["PARALLEL_SEGREGATED", "MULTIPLE_PARALLEL"]

def get_airport_taxi_out_minutes(icao: str) -> int:
    """Returns default EXOT (Estimated Taxi-Out Time) in minutes for EOBT <-> ETOT conversion."""
    return int(get_airport_operations(icao).get("taxiOutMinutes", 10))

def get_airport_taxi_in_minutes(icao: str) -> int:
    """Returns default EXIT (Estimated Taxi-In Time) in minutes."""
    return int(get_airport_operations(icao).get("taxiInMinutes", 6))

def get_airport_mixed_mode_occupancy_buffer(icao: str) -> int:
    """Returns runway occupancy buffer in seconds when interleaving arrivals & departures on a single runway."""
    return int(get_airport_operations(icao).get("mixedModeOccupancyBufferSec", 75))

def save_custom_override(section: str, key: str, value: Any) -> None:
    """Persists a user correction or extension into custom_overrides.json."""
    with _LOCK:
        current = _load_json_file(OVERRIDES_CONFIG_FILE)
        if section not in current:
            current[section] = {}
        current[section][key] = value

        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(OVERRIDES_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)

    reload_configuration()

