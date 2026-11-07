"""
Intelligent Route Auto-Fill and Gap Bridging Engine for FF-ICE Flight Plans.
Fills in missing intermediate waypoints and ATS airways between user-selected sequential waypoints
or between aerodromes.
"""
import math
from typing import List, Dict, Any, Tuple, Optional

def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3440.065
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlamb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlamb/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlamb = math.radians(lon2 - lon1)
    y = math.sin(dlamb) * math.cos(phi2)
    x = math.cos(phi1)*math.sin(phi2) - math.sin(phi1)*math.cos(phi2)*math.cos(dlamb)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0

def cross_track_distance_nm(lat: float, lon: float, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3440.065
    d13 = haversine_nm(lat1, lon1, lat, lon) / R
    theta13 = math.radians(initial_bearing(lat1, lon1, lat, lon))
    theta12 = math.radians(initial_bearing(lat1, lon1, lat2, lon2))
    dxt = math.asin(math.sin(d13) * math.sin(theta13 - theta12)) * R
    return abs(dxt)

def along_track_distance_nm(lat: float, lon: float, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3440.065
    d13 = haversine_nm(lat1, lon1, lat, lon) / R
    dxt = cross_track_distance_nm(lat, lon, lat1, lon1, lat2, lon2) / R
    try:
        val = math.cos(d13) / math.cos(dxt)
        val = max(-1.0, min(1.0, val))
        return math.acos(val) * R
    except Exception:
        return 0.0

def autofill_route(
    dep_airport: Dict[str, Any],
    arr_airport: Dict[str, Any],
    selected_waypoints: List[str],
    all_waypoints: Dict[str, Dict[str, Any]],
    routes: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Connects sequential user-selected waypoints, filling in intermediate fixes
    along ATS airway corridors where large gaps exist.
    """
    cleaned_input = [w.strip().upper() for w in selected_waypoints if w.strip()]
    airways_used: List[str] = []
    inserted_waypoints: List[str] = []

    # Step 1: Check known ATS airway route continuity between consecutive waypoints
    expanded_seq: List[str] = []
    for i in range(len(cleaned_input)):
        w1 = cleaned_input[i]
        expanded_seq.append(w1)
        if i < len(cleaned_input) - 1:
            w2 = cleaned_input[i+1]
            # Search if w1 and w2 lie on an ATS airway
            for r_id, r_data in routes.items():
                r_wps = [wp["name"].upper() for wp in r_data.get("waypoints", [])]
                if w1 in r_wps and w2 in r_wps:
                    idx1 = r_wps.index(w1)
                    idx2 = r_wps.index(w2)
                    if abs(idx1 - idx2) > 1:
                        # intermediate airway points exist
                        step = 1 if idx2 > idx1 else -1
                        intermediates = r_wps[idx1 + step : idx2 : step]
                        for im in intermediates:
                            expanded_seq.append(im)
                            inserted_waypoints.append(im)
                        airways_used.append(r_id)
                        break

    # Step 2: Build node chain [DEP, ...expanded_seq, ARR]
    nodes = [{"name": dep_airport["icao"], "lat": dep_airport["latitude"], "lon": dep_airport["longitude"], "isAirport": True}]
    for name in expanded_seq:
        w_obj = all_waypoints.get(name)
        if w_obj:
            nodes.append({"name": name, "lat": w_obj["latitude"], "lon": w_obj["longitude"], "isAirport": False})
    nodes.append({"name": arr_airport["icao"], "lat": arr_airport["latitude"], "lon": arr_airport["longitude"], "isAirport": True})

    # Step 3: Inspect legs between nodes. If distance > 75 NM, auto-fill corridor waypoints
    final_waypoints: List[str] = []
    for i in range(len(nodes) - 1):
        n1 = nodes[i]
        n2 = nodes[i+1]

        if not n1["isAirport"]:
            final_waypoints.append(n1["name"])

        leg_dist = haversine_nm(n1["lat"], n1["lon"], n2["lat"], n2["lon"])
        # Gap threshold: 75 NM
        if leg_dist > 75.0:
            # Search candidate waypoints within 8 NM of corridor
            candidates = []
            for w_name, w_data in all_waypoints.items():
                if w_name in [n1["name"], n2["name"]]: continue
                xt = cross_track_distance_nm(w_data["latitude"], w_data["longitude"], n1["lat"], n1["lon"], n2["lat"], n2["lon"])
                if xt <= 8.5:
                    al = along_track_distance_nm(w_data["latitude"], w_data["longitude"], n1["lat"], n1["lon"], n2["lat"], n2["lon"])
                    # Between 20% and 80% along leg
                    if 0.20 * leg_dist <= al <= 0.80 * leg_dist:
                        candidates.append({
                            "name": w_name,
                            "xt": xt,
                            "al": al,
                            "score": xt + abs(al - (leg_dist / 2.0)) * 0.1
                        })

            if candidates:
                candidates.sort(key=lambda c: c["score"])
                # Pick up to 2 best spaced candidates
                best_first = candidates[0]
                final_waypoints.append(best_first["name"])
                inserted_waypoints.append(best_first["name"])

                # If very long leg (> 160 NM), pick a second candidate separated by at least 40 NM
                if leg_dist > 160.0:
                    second = next((c for c in candidates[1:] if abs(c["al"] - best_first["al"]) > 40.0), None)
                    if second:
                        # Order by along-track distance
                        if second["al"] < best_first["al"]:
                            final_waypoints.insert(len(final_waypoints) - 1, second["name"])
                        else:
                            final_waypoints.append(second["name"])
                        inserted_waypoints.append(second["name"])

    # If the last node was not airport, add it (should already be covered)
    # Deduplicate consecutive waypoints
    deduped: List[str] = []
    for w in final_waypoints:
        if not deduped or deduped[-1] != w:
            deduped.append(w)

    # Compile waypoint details
    wps_data = []
    for w in deduped:
        obj = all_waypoints.get(w)
        if obj:
            wps_data.append(obj)

    return {
        "originalWaypoints": cleaned_input,
        "filledWaypoints": deduped,
        "waypointsData": wps_data,
        "insertedWaypoints": list(set(inserted_waypoints)),
        "airwaysUsed": list(set(airways_used)),
        "insertedCount": len(set(inserted_waypoints))
    }

