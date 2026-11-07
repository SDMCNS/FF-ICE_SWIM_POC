"""
4D Trajectory & Performance Calculation Engine in Python.
"""
from datetime import datetime, timedelta
import math
from typing import Dict, List, Optional, Tuple, Any
from .aero_data import (
    haversine_distance_nm, initial_bearing_deg, interpolate_point, is_point_in_polygon
)
from .weather import determine_active_runway, parse_runway_heading

def destination_point(lat: float, lon: float, dist_nm: float, bearing_deg: float) -> Tuple[float, float]:
    """
    Calculates latitude and longitude of a destination point given starting point,
    distance in NM, and initial bearing in degrees.
    """
    R = 3440.065 # Earth radius in NM
    d = dist_nm / R
    b = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)

    lat2 = math.asin(
        math.sin(lat1) * math.cos(d) +
        math.cos(lat1) * math.sin(d) * math.cos(b)
    )
    lon2 = lon1 + math.atan2(
        math.sin(b) * math.sin(d) * math.cos(lat1),
        math.cos(d) - math.sin(lat1) * math.sin(lat2)
    )
    return math.degrees(lat2), math.degrees(lon2)

from .config_loader import (
    get_aircraft_perf as _get_loaded_aircraft_perf,
    get_aircraft_database,
    get_airport_taxi_out_minutes,
    get_airport_taxi_in_minutes,
    get_airport_runway_mode
)

# Dynamic aircraft performance loaded from config/aircraft_performance.json and custom_overrides.json
def get_aircraft_perf(ac_type: str) -> Dict[str, Any]:
    return _get_loaded_aircraft_perf(ac_type)

class _DynamicAircraftPerfDict(dict):
    """Dynamically routes dictionary lookups to the loadable JSON configuration."""
    def __getitem__(self, key):
        return get_aircraft_perf(key)
    def get(self, key, default=None):
        res = get_aircraft_perf(key)
        return res if res else default
    def values(self):
        return get_aircraft_database().values()
    def items(self):
        return get_aircraft_database().items()
    def keys(self):
        return get_aircraft_database().keys()
    def __contains__(self, key):
        return key.upper() in get_aircraft_database()
    def __len__(self):
        return len(get_aircraft_database())

AIRCRAFT_PERF = _DynamicAircraftPerfDict()

def check_sanity(
    dep_elev_ft: int,
    dest_elev_ft: int,
    total_dist_nm: float,
    requested_fl: int,
    ac: Dict[str, Any],
    initial_brg: float
) -> Dict[str, Any]:
    errors = []
    warnings = []
    cruise_alt_ft = requested_fl * 100

    if requested_fl > ac["ceiling"]:
        errors.append(f"Requested level FL{requested_fl} exceeds aircraft service ceiling FL{ac['ceiling']}.")

    climb_gain = max(0, cruise_alt_ft - dep_elev_ft)
    climb_min = climb_gain / ac["climbRate"]
    climb_dist_nm = (climb_min / 60.0) * ac["climbSpeed"]

    descent_loss = max(0, cruise_alt_ft - dest_elev_ft)
    descent_dist_nm = descent_loss / ac["descentGrad"]

    min_cruise_buffer = 15.0
    min_req_dist = climb_dist_nm + descent_dist_nm + min_cruise_buffer
    rec_fl = requested_fl

    if min_req_dist > total_dist_nm:
        warnings.append(
            f"Route distance ({total_dist_nm:.1f} NM) is insufficient to reach FL{requested_fl}. Climb and descent require at least {min_req_dist:.1f} NM."
        )
        avail = max(20.0, total_dist_nm - min_cruise_buffer)
        c_factor = ac["climbSpeed"] / (60.0 * ac["climbRate"])
        d_factor = 1.0 / ac["descentGrad"]
        max_achievable_ft = (avail + dep_elev_ft * c_factor + dest_elev_ft * d_factor) / (c_factor + d_factor)
        max_fl = int(max_achievable_ft // 1000) * 10
        rec_fl = min(max_fl, ac["ceiling"])
        rec_fl = max(rec_fl, 40)

    # Semicircular rule
    norm_brg = (initial_brg % 360 + 360) % 360
    expected = "ODD" if (0 <= norm_brg < 180) else "EVEN"
    is_odd = (requested_fl // 10) % 2 == 1
    compliant = (expected == "ODD" and is_odd) or (expected == "EVEN" and not is_odd)

    if not compliant and requested_fl >= 30:
        warnings.append(
            f"FL{requested_fl} does not comply with semicircular rule for track {norm_brg:.0f}° (expected {expected} flight level)."
        )
        rec_is_odd = (rec_fl // 10) % 2 == 1
        if expected == "ODD" and not rec_is_odd:
            rec_fl = max(30, rec_fl - 10)
        elif expected == "EVEN" and rec_is_odd:
            rec_fl = max(40, rec_fl - 10)

    return {
        "isValid": len(errors) == 0,
        "warnings": warnings,
        "errors": errors,
        "recommendedCruiseFl": rec_fl,
        "climbDistanceNm": climb_dist_nm,
        "descentDistanceNm": descent_dist_nm,
        "minimumRequiredDistanceNm": min_req_dist,
        "totalRouteDistanceNm": total_dist_nm,
        "semicircularExpected": expected,
        "semicircularCompliant": compliant
    }

def calculate_4d_trajectory(
    dep_airport: Dict[str, Any],
    arr_airport: Dict[str, Any],
    waypoints: List[Dict[str, Any]],
    aircraft_type: str,
    requested_fl: int,
    eobt_dt: Optional[datetime] = None,
    firs: List[Dict[str, Any]] = None,
    cruise_tas_override: Optional[int] = None,
    departure_runway: Optional[str] = None,
    arrival_runway: Optional[str] = None,
    etot_dt: Optional[datetime] = None
) -> Dict[str, Any]:
    ac = get_aircraft_perf(aircraft_type)
    if firs is None:
        firs = []

    dep_icao = dep_airport.get("icao", "EGLL").upper()
    arr_icao = arr_airport.get("icao", "EIDW").upper()
    exot = get_airport_taxi_out_minutes(dep_icao)
    exit_time = get_airport_taxi_in_minutes(arr_icao)

    # Reconcile EOBT vs ETOT:
    # If ETOT is specified (e.g. from an allocated runway slot), work backwards to calculate EOBT (off-stand pushback).
    # If EOBT is specified, add standard airport taxi-out duration to compute ETOT.
    if etot_dt is not None and eobt_dt is None:
        eobt_dt = etot_dt - timedelta(minutes=exot)
    elif eobt_dt is None and etot_dt is None:
        eobt_dt = datetime.now(timezone.utc).replace(tzinfo=None)
        etot_dt = eobt_dt + timedelta(minutes=exot)
    elif etot_dt is None:
        etot_dt = eobt_dt + timedelta(minutes=exot)

    # Ensure timezone-naive for consistent arithmetic
    if eobt_dt.tzinfo is not None:
        eobt_dt = eobt_dt.replace(tzinfo=None)
    if etot_dt.tzinfo is not None:
        etot_dt = etot_dt.replace(tzinfo=None)

    # 1. Determine active runways and weather
    dep_wx = determine_active_runway(dep_airport)
    active_dep_des = dep_wx.get("activeRunway", "AUTO")
    chosen_dep_rwy = (
        departure_runway.strip().upper()
        if departure_runway and departure_runway.strip().upper() not in ["AUTO", "ANY", ""]
        else active_dep_des
    )
    dep_rwy_obj = next(
        (r for r in dep_airport.get("runways", []) if (r.get("designator") or r.get("designation") or "").upper() == chosen_dep_rwy),
        None
    )
    dep_rwy_hdg = parse_runway_heading(dep_rwy_obj) if dep_rwy_obj else dep_wx.get("runwayHeading", 270.0)

    arr_wx = determine_active_runway(arr_airport)
    active_arr_des = arr_wx.get("activeRunway", "AUTO")
    chosen_arr_rwy = (
        arrival_runway.strip().upper()
        if arrival_runway and arrival_runway.strip().upper() not in ["AUTO", "ANY", ""]
        else active_arr_des
    )
    arr_rwy_obj = next(
        (r for r in arr_airport.get("runways", []) if (r.get("designator") or r.get("designation") or "").upper() == chosen_arr_rwy),
        None
    )
    arr_rwy_hdg = parse_runway_heading(arr_rwy_obj) if arr_rwy_obj else arr_wx.get("runwayHeading", 270.0)

    dep_elev = dep_airport.get("elevationFeet", 0)
    arr_elev = arr_airport.get("elevationFeet", 0)

    # 2. Compute 5 NM straight departure point (no turning for 5 NM)
    dep_5nm_lat, dep_5nm_lon = destination_point(
        dep_airport["latitude"], dep_airport["longitude"], 5.0, dep_rwy_hdg
    )

    # 3. Compute 17 NM ILS localizer intercept point (reciprocal bearing)
    arr_ils_brg = (arr_rwy_hdg + 180.0) % 360.0
    arr_17nm_lat, arr_17nm_lon = destination_point(
        arr_airport["latitude"], arr_airport["longitude"], 17.0, arr_ils_brg
    )

    # 4. Construct sequential route anchors
    anchors = [
        {
            "name": dep_airport["icao"],
            "lat": dep_airport["latitude"],
            "lon": dep_airport["longitude"],
            "type": "DEPARTURE",
            "runway": chosen_dep_rwy,
            "heading": dep_rwy_hdg
        },
        {
            "name": f"RWY{chosen_dep_rwy}_5NM",
            "lat": dep_5nm_lat,
            "lon": dep_5nm_lon,
            "type": "INITIAL_CLIMB",
            "description": f"RWY {chosen_dep_rwy} 5 NM Straight Departure Corridor (No Turning)"
        }
    ]

    for w in waypoints:
        anchors.append({
            "name": w["name"],
            "lat": w["latitude"],
            "lon": w["longitude"],
            "type": "WAYPOINT"
        })

    anchors.append({
        "name": f"ILS{chosen_arr_rwy}_17NM",
        "lat": arr_17nm_lat,
        "lon": arr_17nm_lon,
        "type": "APPROACH_INTERCEPT",
        "description": f"RWY {chosen_arr_rwy} 17 NM ILS Localizer Intercept & Stabilized Glidepath"
    })

    anchors.append({
        "name": arr_airport["icao"],
        "lat": arr_airport["latitude"],
        "lon": arr_airport["longitude"],
        "type": "DESTINATION",
        "runway": chosen_arr_rwy,
        "heading": arr_rwy_hdg
    })

    # 5. Calculate cumulative segment distances
    cum_dists = [0.0]
    total_dist = 0.0
    for i in range(len(anchors) - 1):
        d = haversine_distance_nm(anchors[i]["lat"], anchors[i]["lon"], anchors[i+1]["lat"], anchors[i+1]["lon"])
        total_dist += d
        cum_dists.append(total_dist)

    d_5nm = cum_dists[1]
    d_ils = cum_dists[-2]

    init_brg = dep_rwy_hdg

    # 6. Sanity check & climb/descent profile
    sanity = check_sanity(dep_elev, arr_elev, total_dist, requested_fl, ac, init_brg)
    effective_fl = sanity["recommendedCruiseFl"]
    cruise_alt_ft = effective_fl * 100

    # 5 NM climb-out altitude (approx 2,400 - 2,800 ft AMSL)
    climb_5nm_gain = min(2600.0, max(1200.0, (cruise_alt_ft - dep_elev) * 0.20))
    alt_5nm = dep_elev + climb_5nm_gain

    # 17 NM ILS intercept altitude (approx 5,100 - 5,400 ft AMSL for 3 deg slope)
    ils_intercept_alt = arr_elev + min(5100.0, 17.0 * 300.0)

    # Remaining climb to TOC
    rem_climb_ft = max(0.0, cruise_alt_ft - alt_5nm)
    climb_min = rem_climb_ft / ac["climbRate"] if ac["climbRate"] > 0 else 0.0
    toc_dist_nm = min(d_5nm + (climb_min / 60.0) * ac["climbSpeed"], max(d_5nm + 1.0, total_dist * 0.48))

    # Descent to ILS intercept
    descent_ft = max(0.0, cruise_alt_ft - ils_intercept_alt)
    descent_dist_nm = min(descent_ft / ac["descentGrad"], total_dist * 0.45)
    tod_dist_nm = max(toc_dist_nm + 1.0, d_ils - descent_dist_nm)

    def get_pos(target_dist: float) -> Tuple[float, float]:
        if target_dist <= 0: return anchors[0]["lat"], anchors[0]["lon"]
        if target_dist >= total_dist: return anchors[-1]["lat"], anchors[-1]["lon"]
        for i in range(len(anchors) - 1):
            s_start, s_end = cum_dists[i], cum_dists[i+1]
            if s_start <= target_dist <= s_end:
                frac = (target_dist - s_start) / (s_end - s_start) if s_end > s_start else 0.0
                return interpolate_point(anchors[i]["lat"], anchors[i]["lon"], anchors[i+1]["lat"], anchors[i+1]["lon"], frac)
        return anchors[-1]["lat"], anchors[-1]["lon"]

    def get_alt(dist: float) -> float:
        if dist <= 0:
            return float(dep_elev)
        if dist >= total_dist:
            return float(arr_elev)

        # Segment 1: Initial 5 NM straight departure climbout
        if dist <= d_5nm:
            frac = dist / d_5nm if d_5nm > 0 else 1.0
            return dep_elev + (alt_5nm - dep_elev) * frac

        # Segment 2: Climb from 5NM to TOC
        elif dist <= toc_dist_nm:
            frac = (dist - d_5nm) / (toc_dist_nm - d_5nm) if toc_dist_nm > d_5nm else 1.0
            return alt_5nm + (cruise_alt_ft - alt_5nm) * frac

        # Segment 3: En-route cruise
        elif dist <= tod_dist_nm:
            return float(cruise_alt_ft)

        # Segment 4: Descent from TOD down to 17 NM ILS Intercept
        elif dist <= d_ils:
            frac = (dist - tod_dist_nm) / (d_ils - tod_dist_nm) if d_ils > tod_dist_nm else 1.0
            return cruise_alt_ft - (cruise_alt_ft - ils_intercept_alt) * frac

        # Segment 5: Stabilized 3-degree ILS Final Approach to touchdown
        else:
            frac = (dist - d_ils) / (total_dist - d_ils) if total_dist > d_ils else 1.0
            return ils_intercept_alt - (ils_intercept_alt - arr_elev) * frac

    def get_speed(dist: float) -> float:
        if dist <= d_5nm:
            return float(min(250, ac["climbSpeed"]))
        if dist < toc_dist_nm:
            return float(ac["climbSpeed"])
        if dist > d_ils:
            # Final approach deceleration from 180 to 140 kts
            frac = (dist - d_ils) / (total_dist - d_ils) if total_dist > d_ils else 1.0
            return float(180 - 40 * frac)
        if dist > tod_dist_nm:
            return float(ac["descentSpeed"])
        return float(cruise_tas_override if cruise_tas_override else ac["cruiseTas"])

    # Raw stops
    stops = []
    # Departure threshold
    stops.append({"type": "DEPARTURE", "name": dep_airport["icao"], "dist": 0.0, "pos": (anchors[0]["lat"], anchors[0]["lon"])})
    # 5 NM straight-out climb fix
    stops.append({"type": "INITIAL_CLIMB", "name": f"RWY{chosen_dep_rwy}_5NM", "dist": d_5nm, "pos": (anchors[1]["lat"], anchors[1]["lon"])})

    # TOC
    toc_lat, toc_lon = get_pos(toc_dist_nm)
    stops.append({"type": "TOC", "name": "TOC", "dist": toc_dist_nm, "pos": (toc_lat, toc_lon)})

    # Intermediate Waypoints
    for i in range(2, len(anchors) - 2):
        stops.append({"type": "WAYPOINT", "name": anchors[i]["name"], "dist": cum_dists[i], "pos": (anchors[i]["lat"], anchors[i]["lon"])})

    # TOD
    tod_lat, tod_lon = get_pos(tod_dist_nm)
    stops.append({"type": "TOD", "name": "TOD", "dist": tod_dist_nm, "pos": (tod_lat, tod_lon)})

    # 17 NM ILS Localizer Intercept fix
    stops.append({"type": "APPROACH_INTERCEPT", "name": f"ILS{chosen_arr_rwy}_17NM", "dist": d_ils, "pos": (anchors[-2]["lat"], anchors[-2]["lon"])})

    # Destination threshold
    stops.append({"type": "DESTINATION", "name": arr_airport["icao"], "dist": total_dist, "pos": (anchors[-1]["lat"], anchors[-1]["lon"])})

    stops.sort(key=lambda s: s["dist"])

    # Deduplicate stops within 0.05 NM
    deduped = []
    for s in stops:
        if not deduped or abs(s["dist"] - deduped[-1]["dist"]) > 0.05:
            deduped.append(s)

    # Compute time & 4D points
    points_4d = []
    cum_time_sec = 0.0
    for i, s in enumerate(deduped):
        alt = get_alt(s["dist"])
        spd = get_speed(s["dist"])

        if i > 0:
            d_dist = s["dist"] - deduped[i-1]["dist"]
            avg_spd = (spd + points_4d[-1]["groundSpeedKnots"]) / 2.0
            leg_sec = (d_dist / avg_spd) * 3600.0 if avg_spd > 0 else 0.0
            cum_time_sec += leg_sec

        pt_time = etot_dt + timedelta(seconds=cum_time_sec)
        fl = round(alt / 100)

        # Identify airspace
        matched_fir = None
        for fir in firs:
            min_fl = fir.get("minFlightLevel", 0)
            max_fl = fir.get("maxFlightLevel", 999)
            if min_fl * 100 <= alt <= max_fl * 100:
                poly = [(v["latitude"], v["longitude"]) for v in fir.get("vertices", [])]
                if is_point_in_polygon(s["pos"][0], s["pos"][1], poly):
                    matched_fir = fir.get("airspaceId")
                    break

        points_4d.append({
            "pointType": s["type"],
            "identifier": s["name"],
            "coordinates": {"latitude": s["pos"][0], "longitude": s["pos"][1]},
            "altitudeFeet": round(alt),
            "flightLevel": fl,
            "cumulativeDistanceNm": round(s["dist"], 2),
            "groundSpeedKnots": round(spd),
            "cumulativeTimeSeconds": round(cum_time_sec),
            "estimatedTimestamp": pt_time.isoformat() + "Z",
            "pointSource": "CALCULATED",
            "associatedAirspace": matched_fir
        })

    toc_pt = next((p for p in points_4d if p["pointType"] == "TOC"), points_4d[0])
    tod_pt = next((p for p in points_4d if p["pointType"] == "TOD"), points_4d[-1])
    dest_pt = points_4d[-1]
    eldt_dt = etot_dt + timedelta(seconds=cum_time_sec)
    eibt_dt = eldt_dt + timedelta(minutes=exit_time)

    return {
        "points": points_4d,
        "totalDistanceNm": round(total_dist, 1),
        "totalFlightTimeMinutes": round(cum_time_sec / 60.0, 1),
        "topOfClimb": toc_pt,
        "topOfDescent": tod_pt,
        "firCrossings": [],
        "sanityResult": sanity,
        "eobt": eobt_dt.isoformat() + "Z",
        "etot": etot_dt.isoformat() + "Z",
        "taxiOutMinutes": exot,
        "eldt": eldt_dt.isoformat() + "Z",
        "eibt": eibt_dt.isoformat() + "Z",
        "taxiInMinutes": exit_time,
        "departureRunwayMode": get_airport_runway_mode(dep_icao),
        "arrivalRunwayMode": get_airport_runway_mode(arr_icao),
        "departureRunway": {
            "designator": chosen_dep_rwy,
            "heading": dep_rwy_hdg,
            "windSummary": dep_wx.get("windSummary", ""),
            "headwindKnots": dep_wx.get("headwindKnots", 0.0),
            "crosswindKnots": dep_wx.get("crosswindKnots", 0.0),
            "rawMetar": dep_wx.get("rawMetar", ""),
            "isCalmOrDefault": dep_wx.get("isCalmOrDefault", False)
        },
        "arrivalRunway": {
            "designator": chosen_arr_rwy,
            "heading": arr_rwy_hdg,
            "windSummary": arr_wx.get("windSummary", ""),
            "headwindKnots": arr_wx.get("headwindKnots", 0.0),
            "crosswindKnots": arr_wx.get("crosswindKnots", 0.0),
            "rawMetar": arr_wx.get("rawMetar", ""),
            "isCalmOrDefault": arr_wx.get("isCalmOrDefault", False)
        }
    }

