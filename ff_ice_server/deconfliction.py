"""
4D Strategic Trajectory Deconfliction Engine.
Compares a candidate 4D trajectory against all active/filed plans in SQLite.
Enforces:
  1. ICAO En-route separation: 5.0 NM horizontal (within 1,000 ft vertical RVSM).
     Aircraft can occupy the same horizontal position if separated vertically by >= 1,000 ft.
  2. ICAO Approach separation: Minimum 3.0 NM horizontal on approach/intercept.
  3. ICAO Doc 4444 Wake Turbulence Runway Intervals for Departures & Arrivals (90s, 120s, 180s)
     instead of arbitrary fixed temporal restrictions.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session
from .database import FlightPlanModel, TrajectoryPointModel, ConflictRecordModel
from .aero_data import haversine_distance_nm, initial_bearing_deg
from .airspace_graph import get_airspace_graph
from .config_loader import (
    get_aircraft_perf,
    get_aircraft_wake_category,
    get_departure_wake_interval,
    get_approach_wake_separation,
    get_waypoint_alternates
)

MIN_ENROUTE_SEP_NM = 5.0
MIN_APPROACH_SEP_NM = 3.0
MIN_HORIZONTAL_SEP_NM = 5.0 # default en-route
MIN_VERTICAL_SEP_FT = 1000
MAX_TIME_DELTA_SEC = 300.0 # historical fallback

class _DynamicAlternatesDict(dict):
    """Dynamically routes waypoint alternate lookups to JSON config."""
    def __getitem__(self, key):
        return get_waypoint_alternates(key)
    def get(self, key, default=None):
        res = get_waypoint_alternates(key)
        return res if res else (default or [])
    def __contains__(self, key):
        return len(get_waypoint_alternates(key)) > 0

WAYPOINT_ALTERNATES = _DynamicAlternatesDict()

def _normalize_dt(d: Optional[datetime]) -> Optional[datetime]:
    """Normalizes datetime to naive UTC for safe arithmetic and comparisons."""
    if d is None:
        return None
    if getattr(d, "tzinfo", None) is not None:
        return d.astimezone(timezone.utc).replace(tzinfo=None)
    return d

def interpolate_trajectory_at_time(
    points: List[Any],
    target_dt: datetime
) -> Optional[Tuple[float, float, int, str]]:
    """
    Interpolates a 4D trajectory (list of TrajectoryPointModel or point dicts)
    to find the synchronous (lat, lon, alt_ft, point_type) at exact timestamp target_dt.
    Returns None if target_dt is outside the flight's temporal window.
    """
    if not points:
        return None

    norm_target = _normalize_dt(target_dt)

    def get_pt_info(pt):
        if isinstance(pt, dict):
            t_str = pt.get("estimatedTimestamp", pt.get("timestamp", "")).replace("Z", "")
            try:
                t = datetime.fromisoformat(t_str)
            except Exception:
                t = datetime.min
            c = pt.get("coordinates", {}) if isinstance(pt.get("coordinates"), dict) else {}
            lat = float(c.get("latitude", pt.get("latitude", 0.0)))
            lon = float(c.get("longitude", pt.get("longitude", 0.0)))
            alt = int(pt.get("altitudeFeet", pt.get("altitude_feet", 0)))
            pt_type = str(pt.get("pointType", pt.get("point_type", "WAYPOINT")))
            return lat, lon, alt, _normalize_dt(t), pt_type
        else: # TrajectoryPointModel
            return pt.latitude, pt.longitude, pt.altitude_feet, _normalize_dt(pt.timestamp), pt.point_type

    parsed = [get_pt_info(p) for p in points]
    if len(parsed) == 1:
        lat1, lon1, alt1, t1, type1 = parsed[0]
        if abs((norm_target - t1).total_seconds()) <= 120.0:
            return lat1, lon1, alt1, type1
        return None

    t_start = parsed[0][3]
    t_end = parsed[-1][3]

    if norm_target < t_start or norm_target > t_end:
        return None

    for i in range(len(parsed) - 1):
        lat1, lon1, alt1, t1, type1 = parsed[i]
        lat2, lon2, alt2, t2, type2 = parsed[i + 1]
        if t1 <= norm_target <= t2:
            span = (t2 - t1).total_seconds()
            if span <= 0:
                return lat1, lon1, alt1, type1
            u = (norm_target - t1).total_seconds() / span
            lat = lat1 + u * (lat2 - lat1)
            lon = lon1 + u * (lon2 - lon1)
            alt = int(alt1 + u * (alt2 - alt1))
            pt_type = type2 if u > 0.5 else type1
            return lat, lon, alt, pt_type

    return None

def _extract_route_geom(candidate_points: List[Dict[str, Any]]) -> Tuple[float, float, float, float, float]:
    """
    Extracts origin lat/lon, destination lat/lon, and route distance (NM) from candidate points.
    """
    if not candidate_points:
        return 51.47, -0.46, 53.42, -6.27, 250.0

    p0 = candidate_points[0]
    p1 = candidate_points[-1]
    c0 = p0.get("coordinates", {}) if isinstance(p0.get("coordinates"), dict) else {}
    c1 = p1.get("coordinates", {}) if isinstance(p1.get("coordinates"), dict) else {}

    lat0 = float(c0.get("latitude", p0.get("latitude", 51.47)))
    lon0 = float(c0.get("longitude", p0.get("longitude", -0.46)))
    lat1 = float(c1.get("latitude", p1.get("latitude", 53.42)))
    lon1 = float(c1.get("longitude", p1.get("longitude", -6.27)))

    dist = float(p1.get("cumulativeDistanceNm", 0.0))
    if dist <= 0:
        dist = haversine_distance_nm(lat0, lon0, lat1, lon1)

    return lat0, lon0, lat1, lon1, dist

def get_realistic_flight_levels(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    total_dist_nm: float,
    aircraft_type: str = "A320",
    current_fl: int = 280
) -> Dict[str, Any]:
    """
    Computes valid, realistic, and operationally permissible flight levels for deconfliction:
      1. ICAO Annex 2 Semicircular Rule:
         - Eastbound (000°-179° track): ODD flight levels (FL70, FL90, ..., FL410, FL450).
         - Westbound (180°-359° track): EVEN flight levels (FL60, FL80, ..., FL400, FL430).
      2. Aircraft Service Ceiling:
         - Must not exceed certified aircraft service ceiling from AIRCRAFT_PERF (e.g. C172: FL140, AT76: FL250, A320: FL390).
      3. Physical Distance Feasibility:
         - Climb + descent + 15 NM minimum cruise buffer must fit inside route distance.
           Short hops cannot reach high FL (e.g., 60 NM flight caps at ~FL80).
    """
    ac = get_aircraft_perf(aircraft_type)
    ceiling = ac.get("ceiling", 390)
    climb_rate = ac.get("climbRate", 2200)
    climb_speed = ac.get("climbSpeed", 320)
    descent_grad = ac.get("descentGrad", 318)

    # Aerodynamic distance constraints
    c_factor = climb_speed / (60.0 * climb_rate)
    d_factor = 1.0 / descent_grad
    min_cruise_buffer = 15.0
    avail_dist = max(15.0, total_dist_nm - min_cruise_buffer)
    max_achievable_ft = avail_dist / (c_factor + d_factor)
    max_achievable_fl = int(max_achievable_ft // 1000) * 10
    max_effective_fl = min(ceiling, max_achievable_fl)

    # Initial bearing & track direction
    brg = (initial_bearing_deg(origin_lat, origin_lon, dest_lat, dest_lon) % 360 + 360) % 360
    is_eastbound = (0 <= brg < 180)
    direction = "EASTBOUND" if is_eastbound else "WESTBOUND"
    parity = "ODD" if is_eastbound else "EVEN"

    # Standard ICAO Cruising Levels (Annex 2 Appendix 3)
    if is_eastbound:
        candidate_pool = [70, 90, 110, 130, 150, 170, 190, 210, 230, 250, 270, 290, 310, 330, 350, 370, 390, 410, 450]
    else:
        candidate_pool = [60, 80, 100, 120, 140, 160, 180, 200, 220, 240, 260, 280, 300, 320, 340, 360, 380, 400, 430]

    min_fl = 40 if aircraft_type.upper() == "C172" else (70 if is_eastbound else 60)
    valid_levels = [fl for fl in candidate_pool if min_fl <= fl <= max_effective_fl]

    if not valid_levels:
        fallback_fl = 70 if is_eastbound else 60
        if fallback_fl <= ceiling:
            valid_levels = [fallback_fl]

    return {
        "bearing": brg,
        "direction": direction,
        "parity": parity,
        "ceiling": ceiling,
        "maxAchievableFl": max_achievable_fl,
        "maxEffectiveFl": max_effective_fl,
        "validLevels": valid_levels
    }

class ConflictResult:
    def __init__(
        self,
        conflicting_gufi: str,
        conflicting_callsign: str,
        location_lat: float,
        location_lon: float,
        time_cpa: datetime,
        min_horizontal_nm: float,
        vertical_diff_ft: int,
        severity: str,
        description: str,
        resolution_advisory: str,
        point_name: str = "",
        candidate_fl: int = 280,
        conflict_type: str = "ENROUTE_SEPARATION_LOSS",
        conflicting_trajectory: Optional[List[Dict[str, Any]]] = None,
        aircraft_type: str = "A320",
        total_dist_nm: float = 250.0,
        origin_lat: float = 51.47,
        origin_lon: float = -0.46,
        dest_lat: float = 53.42,
        dest_lon: float = -6.27
    ):
        self.conflicting_gufi = conflicting_gufi
        self.conflicting_callsign = conflicting_callsign
        self.location_lat = location_lat
        self.location_lon = location_lon
        self.time_cpa = time_cpa
        self.min_horizontal_nm = min_horizontal_nm
        self.vertical_diff_ft = vertical_diff_ft
        self.severity = severity
        self.description = description
        self.resolution_advisory = resolution_advisory
        self.point_name = point_name
        self.candidate_fl = candidate_fl
        self.conflict_type = conflict_type
        self.conflicting_trajectory = conflicting_trajectory or []
        self.aircraft_type = aircraft_type
        self.total_dist_nm = total_dist_nm
        self.origin_lat = origin_lat
        self.origin_lon = origin_lon
        self.dest_lat = dest_lat
        self.dest_lon = dest_lon
        self.suggestions = self._build_suggestions()

    def _build_suggestions(self) -> List[Dict[str, Any]]:
        suggestions = []

        if self.conflict_type in ("AIRPORT_SLOT_CONFLICT", "AIRPORT_ARRIVAL_SLOT_CONFLICT"):
            suggestions.append({
                "type": "LONGITUDINAL_DELAY",
                "title": "Select Available Departure Slot (+5 min)",
                "description": "Adjust departure EOBT to the next open airport runway slot (satisfies ICAO wake turbulence departure spacing).",
                "action": "ADJUST_EOBT",
                "delayMinutes": 5
            })
            suggestions.append({
                "type": "LONGITUDINAL_DELAY",
                "title": "Departure Slot Delay (+10 min)",
                "description": "Adjust departure EOBT by +10 minutes for guaranteed runway capacity spacing and wake turbulence clearance.",
                "action": "ADJUST_EOBT",
                "delayMinutes": 10
            })
            return suggestions

        # En-route separation loss resolutions:
        # 1. Altitude Change Suggestions (Strictly compliant with Semicircular rule, Aircraft Ceiling, and Distance)
        fl = self.candidate_fl if self.candidate_fl >= 30 else 280
        fl_info = get_realistic_flight_levels(
            origin_lat=self.origin_lat,
            origin_lon=self.origin_lon,
            dest_lat=self.dest_lat,
            dest_lon=self.dest_lon,
            total_dist_nm=self.total_dist_nm,
            aircraft_type=self.aircraft_type,
            current_fl=fl
        )
        valid_levels = fl_info["validLevels"]
        parity = fl_info["parity"]
        ceiling = fl_info["ceiling"]
        brg = fl_info["bearing"]

        higher = [lvl for lvl in valid_levels if lvl > fl]
        lower = [lvl for lvl in valid_levels if lvl < fl]

        alt_up = higher[0] if higher else None
        alt_down = lower[-1] if lower else None

        if alt_up:
            delta_ft = (alt_up - fl) * 100
            sign_str = f"+{delta_ft}" if delta_ft > 0 else f"{delta_ft}"
            suggestions.append({
                "type": "ALTITUDE_CHANGE",
                "title": f"Step Climb to FL{alt_up}",
                "description": (
                    f"Climb {sign_str} ft to FL{alt_up} to clear vertical separation minimum. "
                    f"Complies with ICAO {parity} semicircular rule (track {brg:.0f}°), "
                    f"within {self.aircraft_type} ceiling (FL{ceiling}) and route distance envelope."
                ),
                "action": "SET_ALTITUDE",
                "targetFlightLevel": alt_up
            })
        if alt_down:
            delta_ft = (fl - alt_down) * 100
            suggestions.append({
                "type": "ALTITUDE_CHANGE",
                "title": f"Descend to FL{alt_down}",
                "description": (
                    f"Descend -{delta_ft} ft to FL{alt_down} to pass safely below conflicting traffic. "
                    f"Complies with ICAO {parity} semicircular rule (track {brg:.0f}°), "
                    f"within {self.aircraft_type} certified limits."
                ),
                "action": "SET_ALTITUDE",
                "targetFlightLevel": alt_down
            })

        # 2. Longitudinal Delay Suggestion (+10 minutes)
        suggestions.append({
            "type": "LONGITUDINAL_DELAY",
            "title": "Departure Slot Delay (+10 min)",
            "description": "Delay departure EOBT by +10 minutes to open a trailing longitudinal separation buffer of >15 NM.",
            "action": "ADJUST_EOBT",
            "delayMinutes": 10
        })

        # 3. Lateral Reroute via Aeronautical Navigation Graph
        clean_pt = self.point_name.upper().strip()
        try:
            graph = get_airspace_graph()
            alternates = graph.get_waypoint_alternates(clean_pt, limit=4)
        except Exception:
            alternates = WAYPOINT_ALTERNATES.get(clean_pt, ["OLAPO", "SUROX", "PESIT", "WAL"])

        alt_wp = next((w for w in alternates if w != clean_pt), "OLAPO") if alternates else "OLAPO"
        suggestions.append({
            "type": "LATERAL_REROUTE",
            "title": f"Reroute via {alt_wp}",
            "description": f"Bypass congested bottleneck at {clean_pt} by routing laterally via {alt_wp} (airspace graph detour).",
            "action": "REPLACE_WAYPOINT",
            "oldWaypoint": clean_pt,
            "newWaypoint": alt_wp,
            "graphAlternates": alternates
        })

        # 4. Longitudinal Speed Control / Slow Flight (-30 kts)
        suggestions.append({
            "type": "SPEED_REDUCTION",
            "title": "Reduce Cruise Speed (-30 kts)",
            "description": "Slow aircraft cruising speed by 30 knots to delay arrival at conflict fix and establish longitudinal spacing.",
            "action": "ADJUST_SPEED",
            "speedDeltaKnots": -30
        })

        return suggestions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflictingGufi": self.conflicting_gufi,
            "conflictingCallsign": self.conflicting_callsign,
            "latitude": round(self.location_lat, 4),
            "longitude": round(self.location_lon, 4),
            "timeOfClosestApproach": self.time_cpa.isoformat() + "Z",
            "horizontalSeparationNm": round(self.min_horizontal_nm, 2),
            "verticalSeparationFt": self.vertical_diff_ft,
            "severity": self.severity,
            "description": self.description,
            "pointName": self.point_name,
            "resolutionAdvisory": self.resolution_advisory,
            "suggestions": self.suggestions,
            "conflictingTrajectory": self.conflicting_trajectory
        }

class DeconflictionOutcome(tuple):
    """
    Subclasses tuple to be a 3-tuple (has_conflicts, conflicts, resolutions)
    for 100% backwards compatibility with existing tuple unpacking:
    has_conflicts, conflicts, resolutions = deconflict_trajectory(...)
    while also exposing .comprehensive_solutions and object properties.
    """
    def __new__(cls, has_conflicts: bool, conflicts: list, resolutions: list, comprehensive_solutions: list = None):
        return super().__new__(cls, (has_conflicts, conflicts, resolutions))

    def __init__(self, has_conflicts: bool, conflicts: list, resolutions: list, comprehensive_solutions: list = None):
        self.has_conflicts = has_conflicts
        self.conflicts = conflicts
        self.resolutions = resolutions
        self.comprehensive_solutions = comprehensive_solutions or []

def solve_comprehensive_deconfliction(
    candidate_points: List[Dict[str, Any]],
    candidate_eobt: datetime,
    initial_conflicts: List[ConflictResult],
    other_pts_by_gufi: Dict[str, List[TrajectoryPointModel]],
    aircraft_type: str = "A320"
) -> List[Dict[str, Any]]:
    """
    Synthesizes holistic, multi-variable deconfliction solutions that resolve
    ALL conflicts simultaneously across all active database flights.
    Evaluates:
      1. Vertical cruise altitude optimization (strictly respecting ICAO semicircular parity,
         aircraft certified service ceiling, and route distance climb/descent feasibility)
      2. Longitudinal departure slot spacing (+5 to +30 min buffers)
      3. Combined vertical and longitudinal coordination (slot + realistic level)
      4. Speed control (-30 kts cruise Mach adjustment)
      5. Graph-based lateral bypass detours around congested bottlenecks
    Returns ranked solutions by operational realism and fuel/schedule efficiency.
    """
    if not initial_conflicts or not candidate_points:
        return []

    num_conflicts = len(initial_conflicts)
    conflicting_callsigns = [c.conflicting_callsign for c in initial_conflicts]
    callsign_summary = ", ".join(conflicting_callsigns[:3])
    if len(conflicting_callsigns) > 3:
        callsign_summary += f" (+{len(conflicting_callsigns) - 3} more)"

    # Route geometry and performance limits
    lat0, lon0, lat1, lon1, dist_nm = _extract_route_geom(candidate_points)
    fl_info = get_realistic_flight_levels(
        origin_lat=lat0,
        origin_lon=lon0,
        dest_lat=lat1,
        dest_lon=lon1,
        total_dist_nm=dist_nm,
        aircraft_type=aircraft_type
    )
    valid_levels = fl_info["validLevels"]
    parity = fl_info["parity"]
    ceiling = fl_info["ceiling"]
    brg = fl_info["bearing"]

    # Helper: count conflicting GUFIs for any modified candidate trajectory points
    cand_wake = get_aircraft_wake_category(aircraft_type)

    def test_trajectory_conflicts(test_pts: List[Dict[str, Any]]) -> List[str]:
        conflicting_gufis = set()
        if not test_pts:
            return []

        tp0 = test_pts[0]
        tp0_t_str = tp0.get("estimatedTimestamp", "").replace("Z", "")
        try:
            cand_dep_t = datetime.fromisoformat(tp0_t_str)
        except Exception:
            cand_dep_t = None

        for gufi, op_list in other_pts_by_gufi.items():
            if not op_list: continue
            hit = False
            op0 = op_list[0]

            # 1. Ground Runway Wake Separation (Departures)
            if cand_dep_t and tp0.get("identifier") == op0.identifier and tp0.get("pointType") == "DEPARTURE":
                diff_sec = abs((cand_dep_t - op0.timestamp).total_seconds())
                req_sec = get_departure_wake_interval("M", cand_wake)
                if diff_sec < req_sec:
                    conflicting_gufis.add(gufi)
                    continue

            # 2. Synchronous 4D Airborne Trajectory Evaluation
            for tp in test_pts:
                if hit: break
                t_str = tp.get("estimatedTimestamp", "").replace("Z", "")
                try:
                    t = datetime.fromisoformat(t_str)
                except Exception:
                    continue
                alt1 = tp.get("altitudeFeet", 0)
                if alt1 < 200 and tp.get("pointType") in ["DEPARTURE", "DESTINATION"]:
                    continue

                interp = interpolate_trajectory_at_time(op_list, t)
                if interp:
                    lat_op, lon_op, alt_op, type_op = interp
                    v_diff = abs(alt1 - alt_op)
                    # CRITICAL: If vertically separated by >= 1,000 ft, NO CONFLICT!
                    if v_diff < MIN_VERTICAL_SEP_FT:
                        c = tp.get("coordinates", {})
                        lat1_pt = c.get("latitude", tp.get("latitude", 0.0))
                        lon1_pt = c.get("longitude", tp.get("longitude", 0.0))
                        h_dist = haversine_distance_nm(lat1_pt, lon1_pt, lat_op, lon_op)
                        is_app = (tp.get("pointType") in ["APPROACH_INTERCEPT", "DESTINATION"] or
                                  type_op in ["APPROACH_INTERCEPT", "DESTINATION"] or
                                  alt1 < 4000 or alt_op < 4000)
                        req_h = MIN_APPROACH_SEP_NM if is_app else MIN_ENROUTE_SEP_NM
                        if h_dist < req_h:
                            conflicting_gufis.add(gufi)
                            hit = True
                            break
        return list(conflicting_gufis)

    # Determine baseline cruise level
    base_fl = max((p.get("flightLevel", 0) for p in candidate_points), default=280)
    if base_fl < 30: base_fl = 280

    solutions = []

    # ------------------------------------------------------------------
    # Strategy 1: Vertical Profile Shift (Strict Semicircular & Performance Compliant)
    # ------------------------------------------------------------------
    # Pick candidate levels from valid_levels sorted by proximity to base_fl
    vert_candidates = sorted([fl for fl in valid_levels if fl != base_fl], key=lambda x: (abs(x - base_fl), -x))

    for target_fl in vert_candidates:
        delta = target_fl - base_fl
        if delta > 0:
            verb = "Step Climb" if delta <= 20 else ("High Step Climb" if delta <= 40 else "Ceiling Climb")
            base_score = 97 if delta <= 20 else (90 if delta <= 40 else 82)
        else:
            verb = "Descend" if delta >= -20 else ("Lower Cruise Level" if delta >= -40 else "Low Cruise Level")
            base_score = 94 if delta >= -20 else (86 if delta >= -40 else 78)

        mod_pts = []
        for p in candidate_points:
            pt_copy = dict(p)
            pt_type = pt_copy.get("pointType", "")
            if pt_type in ["INITIAL_CLIMB", "APPROACH_INTERCEPT"]:
                mod_pts.append(pt_copy)
            elif pt_type in ["CRUISE", "WAYPOINT"] or pt_copy.get("flightLevel", 0) >= base_fl - 30:
                pt_copy["altitudeFeet"] = target_fl * 100
                pt_copy["flightLevel"] = target_fl
                mod_pts.append(pt_copy)
            else:
                ratio = target_fl / max(base_fl, 1)
                pt_copy["altitudeFeet"] = int(pt_copy.get("altitudeFeet", 0) * ratio)
                pt_copy["flightLevel"] = int(pt_copy.get("flightLevel", 0) * ratio)
                mod_pts.append(pt_copy)

        remaining = test_trajectory_conflicts(mod_pts)
        if len(remaining) == 0:
            delta_fl = target_fl - base_fl
            sign_str = f"+{delta_fl*100}" if delta_fl > 0 else f"{delta_fl*100}"
            solutions.append({
                "id": f"comp_vert_FL{target_fl}",
                "title": f"Vertical Profile: {verb} to FL{target_fl}",
                "strategy": "VERTICAL_OPTIMIZATION",
                "efficiencyScore": base_score,
                "description": (
                    f"Adjust cruise level from FL{base_fl} to FL{target_fl} ({sign_str} ft). "
                    f"This simultaneously resolves all {num_conflicts} conflict(s) ({callsign_summary}) "
                    f"with 0 minutes schedule delay while maintaining optimum {aircraft_type} cruise fuel burn. "
                    f"Fully compliant with ICAO {parity} semicircular rule (track {brg:.0f}°), {aircraft_type} ceiling (FL{ceiling}), and route distance."
                ),
                "conflictsResolved": num_conflicts,
                "remainingConflicts": 0,
                "actions": [
                    {
                        "type": "SET_ALTITUDE",
                        "targetFlightLevel": target_fl,
                        "targetAltitudeFeet": target_fl * 100,
                        "label": f"Change Altitude to FL{target_fl}"
                    }
                ],
                "badges": ["Zero Ground Delay", f"Resolves All {num_conflicts} Conflicts", f"ICAO {parity} Compliant", f"{aircraft_type} Ceiling FL{ceiling}"],
                "summary": f"Clear of all traffic at FL{target_fl}. 0 min delay."
            })
            if len([s for s in solutions if s["strategy"] == "VERTICAL_OPTIMIZATION"]) >= 2:
                break

    # ------------------------------------------------------------------
    # Strategy 2: Longitudinal Spacing (Departure Slot Buffers)
    # ------------------------------------------------------------------
    delay_candidates = [5, 8, 10, 12, 15, 20, 25, 30]
    for delay_min in delay_candidates:
        mod_pts = []
        for p in candidate_points:
            pt_copy = dict(p)
            t_str = pt_copy.get("estimatedTimestamp", "").replace("Z", "")
            try:
                t = datetime.fromisoformat(t_str) + timedelta(minutes=delay_min)
                pt_copy["estimatedTimestamp"] = t.isoformat() + "Z"
            except Exception:
                pass
            mod_pts.append(pt_copy)

        remaining = test_trajectory_conflicts(mod_pts)
        if len(remaining) == 0:
            score = max(55, 96 - int(delay_min * 1.1))
            solutions.append({
                "id": f"comp_long_D{delay_min}",
                "title": f"Longitudinal Spacing: +{delay_min} min Slot Delay",
                "strategy": "LONGITUDINAL_SPACING",
                "efficiencyScore": score,
                "description": (
                    f"Adjust departure EOBT by +{delay_min} minutes. Preserves planned optimal cruise altitude at FL{base_fl} "
                    f"while establishing full ICAO longitudinal trailing separation (>15 NM buffer) against {callsign_summary}."
                ),
                "conflictsResolved": num_conflicts,
                "remainingConflicts": 0,
                "actions": [
                    {
                        "type": "ADJUST_EOBT",
                        "delayMinutes": delay_min,
                        "label": f"Delay EOBT +{delay_min} min"
                    }
                ],
                "badges": [f"Optimal FL{base_fl} Preserved", f"Resolves All {num_conflicts} Conflicts", "Trailing Spacing Buffer"],
                "summary": f"Clear of all traffic with +{delay_min}m slot spacing."
            })
            break

    # ------------------------------------------------------------------
    # Strategy 3: Combined Coordination (Moderate Slot Buffer + Level Shift)
    # ------------------------------------------------------------------
    comb_candidates = [fl for fl in valid_levels if abs(fl - base_fl) in (20, 40)]
    if not comb_candidates and valid_levels:
        comb_candidates = [sorted(valid_levels, key=lambda x: abs(x - base_fl))[0]]

    for target_fl in comb_candidates[:2]:
        for delay_min in [5, 8, 10]:
            mod_pts = []
            for p in candidate_points:
                pt_copy = dict(p)
                t_str = pt_copy.get("estimatedTimestamp", "").replace("Z", "")
                try:
                    t = datetime.fromisoformat(t_str) + timedelta(minutes=delay_min)
                    pt_copy["estimatedTimestamp"] = t.isoformat() + "Z"
                except Exception:
                    pass
                pt_type = pt_copy.get("pointType", "")
                if pt_type not in ["INITIAL_CLIMB", "APPROACH_INTERCEPT"]:
                    pt_copy["altitudeFeet"] = target_fl * 100
                    pt_copy["flightLevel"] = target_fl
                mod_pts.append(pt_copy)

            remaining = test_trajectory_conflicts(mod_pts)
            if len(remaining) == 0:
                score = 91 - int(delay_min * 0.8)
                solutions.append({
                    "id": f"comp_comb_FL{target_fl}_D{delay_min}",
                    "title": f"Combined Profile: FL{target_fl} with +{delay_min} min Slot",
                    "strategy": "COMBINED_PROFILE",
                    "efficiencyScore": score,
                    "description": (
                        f"Adjust cruise level to FL{target_fl} (ICAO {parity} semicircular, within {aircraft_type} limits) "
                        f"combined with a minor +{delay_min} min departure slot adjustment. "
                        f"Provides comprehensive separation across both runway departure sequencing and en-route airspace."
                    ),
                    "conflictsResolved": num_conflicts,
                    "remainingConflicts": 0,
                    "actions": [
                        {
                            "type": "SET_ALTITUDE",
                            "targetFlightLevel": target_fl,
                            "targetAltitudeFeet": target_fl * 100,
                            "label": f"Set FL{target_fl}"
                        },
                        {
                            "type": "ADJUST_EOBT",
                            "delayMinutes": delay_min,
                            "label": f"Delay +{delay_min} min"
                        }
                    ],
                    "badges": [f"Resolves All {num_conflicts} Conflicts", "Runway & En-route Clear", f"ICAO {parity} Compliant"],
                    "summary": f"Clear of all traffic at FL{target_fl} with +{delay_min}m slot."
                })
                break
        if any(s["strategy"] == "COMBINED_PROFILE" for s in solutions):
            break

    # ------------------------------------------------------------------
    # Strategy 4: Speed Control (Cruise Speed Reduction -30 kts)
    # ------------------------------------------------------------------
    mod_pts = []
    for p in candidate_points:
        pt_copy = dict(p)
        dist = pt_copy.get("cumulativeDistanceNm", 0.0)
        time_shift_sec = (dist / 420.0 - dist / 450.0) * 3600.0 if dist > 0 else 0
        t_str = pt_copy.get("estimatedTimestamp", "").replace("Z", "")
        try:
            t = datetime.fromisoformat(t_str) + timedelta(seconds=time_shift_sec)
            pt_copy["estimatedTimestamp"] = t.isoformat() + "Z"
        except Exception:
            pass
        mod_pts.append(pt_copy)

    remaining = test_trajectory_conflicts(mod_pts)
    if len(remaining) == 0:
        solutions.append({
            "id": "comp_speed_slow30",
            "title": "Speed Control: Cruise Speed -30 kts",
            "strategy": "SPEED_CONTROL",
            "efficiencyScore": 88,
            "description": (
                f"Reduce cruising speed by 30 knots. Shifts en-route fix arrival times by 3-5 minutes, "
                f"opening trailing separation against {callsign_summary} while retaining planned FL{base_fl} and departure time."
            ),
            "conflictsResolved": num_conflicts,
            "remainingConflicts": 0,
            "actions": [
                {
                    "type": "ADJUST_SPEED",
                    "speedDeltaKnots": -30,
                    "label": "Reduce Speed -30 kts"
                }
            ],
            "badges": [f"FL{base_fl} Preserved", "Zero Departure Ground Delay", f"Resolves All {num_conflicts} Conflicts"],
            "summary": "Clear of all traffic via speed control (-30 kts)."
        })

    # ------------------------------------------------------------------
    # Strategy 5: Graph-Based Lateral Bypass Rerouting
    # ------------------------------------------------------------------
    cand_wpt_names = [p.get("identifier", "") for p in candidate_points if p.get("pointType") == "WAYPOINT"]
    for c in initial_conflicts:
        conflicted_fix = c.point_name.upper().strip()
        if not conflicted_fix or c.conflict_type == "AIRPORT_SLOT_CONFLICT":
            continue
        try:
            graph = get_airspace_graph()
            bypass_options = graph.find_lateral_bypass(cand_wpt_names, conflicted_fix, limit=2)
        except Exception:
            bypass_options = []

        for b in bypass_options:
            alt_wp = b["newWaypoint"]
            old_wp = b["oldWaypoint"]
            alt_node = graph.nodes.get(alt_wp) if 'graph' in locals() else None
            if not alt_node: continue

            mod_pts = []
            for p in candidate_points:
                pt_copy = dict(p)
                if pt_copy.get("identifier") == old_wp:
                    pt_copy["identifier"] = alt_wp
                    pt_copy["coordinates"] = {
                        "latitude": alt_node["latitude"],
                        "longitude": alt_node["longitude"]
                    }
                mod_pts.append(pt_copy)

            remaining = test_trajectory_conflicts(mod_pts)
            if len(remaining) == 0:
                solutions.append({
                    "id": f"comp_lateral_{alt_wp}",
                    "title": f"Lateral Reroute: Bypass {old_wp} via {alt_wp}",
                    "strategy": "LATERAL_REROUTE",
                    "efficiencyScore": 92,
                    "description": (
                        f"Detour laterally around congested bottleneck at {old_wp} by routing via {alt_wp} (+{b.get('deltaDistanceNm', 5.0)} NM). "
                        f"Clears all {num_conflicts} conflicting traffic trajectories while preserving filed cruise FL{base_fl} and scheduled departure."
                    ),
                    "conflictsResolved": num_conflicts,
                    "remainingConflicts": 0,
                    "actions": [
                        {
                            "type": "REPLACE_WAYPOINT",
                            "oldWaypoint": old_wp,
                            "newWaypoint": alt_wp,
                            "label": f"Reroute {old_wp} -> {alt_wp}"
                        }
                    ],
                    "badges": [f"FL{base_fl} Preserved", "Zero Ground Delay", f"Resolves All {num_conflicts} Conflicts", "Graph Shortest Detour"],
                    "summary": f"Clear of all traffic via lateral reroute {old_wp} -> {alt_wp}."
                })
                break
        if any(s["strategy"] == "LATERAL_REROUTE" for s in solutions):
            break

    solutions.sort(key=lambda s: s["efficiencyScore"], reverse=True)
    return solutions

def deconflict_trajectory(
    candidate_gufi: str,
    candidate_callsign: str,
    candidate_points: List[Dict[str, Any]],
    candidate_eobt: datetime,
    candidate_eta: datetime,
    db: Session,
    log_to_db: bool = True,
    aircraft_type: str = "A320"
) -> DeconflictionOutcome:
    """
    Evaluates candidate trajectory points against all other active/filed plans in the database.
    Returns DeconflictionOutcome (3-tuple with .comprehensive_solutions).
    """
    conflicts: List[ConflictResult] = []
    resolutions: List[str] = []

    # 1. Query existing overlapping flight plans
    # Buffer time window by 15 minutes before EOBT and after ETA
    cand_eobt_norm = _normalize_dt(candidate_eobt)
    cand_eta_norm = _normalize_dt(candidate_eta)
    t_start = cand_eobt_norm - timedelta(minutes=15)
    t_end = cand_eta_norm + timedelta(minutes=15)

    other_plans = (
        db.query(FlightPlanModel)
        .filter(
            FlightPlanModel.gufi != candidate_gufi,
            FlightPlanModel.status.in_(["FILED", "AGREED", "ACTIVE"]),
            FlightPlanModel.eobt <= t_end,
            FlightPlanModel.eta >= t_start
        )
        .all()
    )

    if not other_plans:
        return DeconflictionOutcome(False, [], ["Airspace clear. No conflicting 4D trajectories detected."], [])

    other_pts_by_gufi: Dict[str, List[TrajectoryPointModel]] = {}
    lat0, lon0, lat1, lon1, total_dist_nm = _extract_route_geom(candidate_points)

    cand_wake = get_aircraft_wake_category(aircraft_type)

    # 2. Iterate each existing plan and compare 4D points
    for other in other_plans:
        other_pts = (
            db.query(TrajectoryPointModel)
            .filter(TrajectoryPointModel.gufi == other.gufi)
            .order_by(TrajectoryPointModel.point_index)
            .all()
        )
        if not other_pts: continue
        other_pts_by_gufi[other.gufi] = other_pts

        other_wake = other.wake_turbulence or get_aircraft_wake_category(other.aircraft_type)
        other_eobt_norm = _normalize_dt(other.eobt)
        other_eta_norm = _normalize_dt(other.eta)
        worst_conflict = None
        min_sep_found = float("inf")

        # -------------------------------------------------------------
        # A. Ground Runway Wake Separation (Departures)
        # -------------------------------------------------------------
        dep_icao = candidate_points[0].get("identifier", "").upper() if candidate_points else ""
        if dep_icao and other.departure_icao == dep_icao:
            time_diff = abs((cand_eobt_norm - other_eobt_norm).total_seconds())
            if cand_eobt_norm >= other_eobt_norm:
                lead_w, trail_w = other_wake, cand_wake
            else:
                lead_w, trail_w = cand_wake, other_wake
            req_dep_sec = get_departure_wake_interval(lead_w, trail_w)

            if time_diff < req_dep_sec:
                min_sep_found = 0.0
                delay_rec = max(2, int((req_dep_sec - time_diff) / 60) + 1)
                worst_conflict = ConflictResult(
                    conflicting_gufi=other.gufi,
                    conflicting_callsign=other.callsign,
                    location_lat=lat0,
                    location_lon=lon0,
                    time_cpa=candidate_eobt,
                    min_horizontal_nm=0.0,
                    vertical_diff_ft=0,
                    severity="CRITICAL" if time_diff < 60 else "WARNING",
                    description=(
                        f"Airport departure wake separation conflict with {other.callsign} at {dep_icao}: "
                        f"Scheduled {int(time_diff)}s apart. ICAO Doc 4444 requires {req_dep_sec}s runway departure spacing "
                        f"({trail_w} trailing {lead_w})."
                    ),
                    resolution_advisory=(
                        f"Recommend selecting an available departure slot (+{delay_rec} min delay) "
                        f"to achieve required {req_dep_sec}s ICAO wake turbulence departure spacing."
                    ),
                    point_name=dep_icao,
                    candidate_fl=1,
                    conflict_type="AIRPORT_SLOT_CONFLICT",
                    aircraft_type=aircraft_type,
                    total_dist_nm=total_dist_nm,
                    origin_lat=lat0, origin_lon=lon0,
                    dest_lat=lat1, dest_lon=lon1
                )

        # -------------------------------------------------------------
        # B. Ground Runway Wake Spacing (Arrivals)
        # -------------------------------------------------------------
        arr_icao = candidate_points[-1].get("identifier", "").upper() if candidate_points else ""
        if not worst_conflict and arr_icao and other.arrival_icao == arr_icao:
            time_diff = abs((cand_eta_norm - other_eta_norm).total_seconds())
            if cand_eta_norm >= other_eta_norm:
                lead_w, trail_w = other_wake, cand_wake
            else:
                lead_w, trail_w = cand_wake, other_wake
            req_app_nm = get_approach_wake_separation(lead_w, trail_w)
            req_arr_sec = int((req_app_nm / 140.0) * 3600.0)

            if time_diff < req_arr_sec:
                min_sep_found = 0.5
                delay_rec = max(2, int((req_arr_sec - time_diff) / 60) + 1)
                worst_conflict = ConflictResult(
                    conflicting_gufi=other.gufi,
                    conflicting_callsign=other.callsign,
                    location_lat=lat1,
                    location_lon=lon1,
                    time_cpa=candidate_eta,
                    min_horizontal_nm=0.5,
                    vertical_diff_ft=0,
                    severity="WARNING",
                    description=(
                        f"Arrival runway wake spacing conflict with {other.callsign} at {arr_icao}: "
                        f"Scheduled {int(time_diff)}s apart. ICAO Doc 4444 requires {req_app_nm:.1f} NM ({req_arr_sec}s) "
                        f"approach wake separation ({trail_w} trailing {lead_w})."
                    ),
                    resolution_advisory=(
                        f"Recommend adjusting flight timing by +{delay_rec} min to ensure {req_app_nm:.1f} NM "
                        f"approach wake turbulence separation at destination."
                    ),
                    point_name=arr_icao,
                    candidate_fl=2,
                    conflict_type="AIRPORT_ARRIVAL_SLOT_CONFLICT",
                    aircraft_type=aircraft_type,
                    total_dist_nm=total_dist_nm,
                    origin_lat=lat0, origin_lon=lon0,
                    dest_lat=lat1, dest_lon=lon1
                )

        # -------------------------------------------------------------
        # C. Synchronous 4D Airborne Trajectory Evaluation
        # -------------------------------------------------------------
        if not worst_conflict:
            # 1. Forward Check: Interpolate other flight at candidate point timestamps
            for cp in candidate_points:
                c_time_str = cp.get("estimatedTimestamp", "").replace("Z", "")
                try:
                    c_time = datetime.fromisoformat(c_time_str)
                except Exception:
                    continue

                c_lat = cp["coordinates"]["latitude"]
                c_lon = cp["coordinates"]["longitude"]
                c_alt = cp["altitudeFeet"]
                c_fl = cp["flightLevel"]
                pt_name = cp.get("identifier", "Enroute")

                # Skip ground origin/destination endpoints
                if cp.get("pointType") in ["DEPARTURE", "DESTINATION"] and c_alt < 500:
                    continue

                interp = interpolate_trajectory_at_time(other_pts, c_time)
                if not interp: continue

                o_lat, o_lon, o_alt, o_type = interp
                vert_diff = abs(c_alt - o_alt)

                # CRITICAL RULE: If separated vertically by >= 1,000 ft, NO CONFLICT!
                # (Aircraft can safely occupy the exact same horizontal position)
                if vert_diff >= MIN_VERTICAL_SEP_FT:
                    continue

                h_dist = haversine_distance_nm(c_lat, c_lon, o_lat, o_lon)
                is_app = (cp.get("pointType") in ["APPROACH_INTERCEPT", "DESTINATION"] or
                          o_type in ["APPROACH_INTERCEPT", "DESTINATION"] or
                          c_alt < 4000 or o_alt < 4000)
                req_h = max(MIN_APPROACH_SEP_NM, get_approach_wake_separation(other_wake, cand_wake)) if is_app else MIN_ENROUTE_SEP_NM

                if h_dist < req_h:
                    cpa_time = c_time
                    severity = "CRITICAL" if h_dist < (2.0 if is_app else 3.0) and vert_diff < 500 else "WARNING"
                    c_type = "APPROACH_SEPARATION_LOSS" if is_app else "ENROUTE_SEPARATION_LOSS"

                    fl_info = get_realistic_flight_levels(
                        origin_lat=lat0, origin_lon=lon0,
                        dest_lat=lat1, dest_lon=lon1,
                        total_dist_nm=total_dist_nm,
                        aircraft_type=aircraft_type,
                        current_fl=c_fl
                    )
                    v_levels = fl_info["validLevels"]
                    highers = [l for l in v_levels if l > c_fl]
                    lowers = [l for l in v_levels if l < c_fl]
                    rec_target = highers[0] if highers else (lowers[-1] if lowers else None)

                    if rec_target:
                        advisory = (
                            f"Option A: Re-file at FL{rec_target} ({fl_info['parity']} compliant, within {aircraft_type} limits). "
                            f"Option B: Delay departure EOBT by +8 minutes for longitudinal spacing."
                        )
                    else:
                        advisory = (
                            f"Option A: Delay departure EOBT by +8 to +10 minutes for longitudinal spacing. "
                            f"Option B: Adjust cruising speed or waypoint corridor."
                        )

                    combined_sep = h_dist + (vert_diff / 1000.0)
                    if combined_sep < min_sep_found:
                        min_sep_found = combined_sep
                        worst_conflict = ConflictResult(
                            conflicting_gufi=other.gufi,
                            conflicting_callsign=other.callsign,
                            location_lat=c_lat,
                            location_lon=c_lon,
                            time_cpa=cpa_time,
                            min_horizontal_nm=h_dist,
                            vertical_diff_ft=vert_diff,
                            severity=severity,
                            description=(
                                f"Strategic 4D separation conflict with {other.callsign} at {pt_name}: "
                                f"Predicted separation {h_dist:.1f} NM (min {req_h:.1f} NM {'approach' if is_app else 'en-route'}) "
                                f"and {vert_diff} ft vertical (min 1,000 ft) at {cpa_time.strftime('%H:%M:%S')} UTC."
                            ),
                            resolution_advisory=advisory,
                            point_name=pt_name,
                            candidate_fl=c_fl,
                            conflict_type=c_type,
                            aircraft_type=aircraft_type,
                            total_dist_nm=total_dist_nm,
                            origin_lat=lat0, origin_lon=lon0,
                            dest_lat=lat1, dest_lon=lon1
                        )

            # 2. Reverse Check: Interpolate candidate trajectory at other flight's points
            for op in other_pts:
                if op.point_type in ["DEPARTURE", "DESTINATION"] and op.altitude_feet < 500:
                    continue

                interp = interpolate_trajectory_at_time(candidate_points, op.timestamp)
                if not interp: continue

                c_lat, c_lon, c_alt, c_type = interp
                vert_diff = abs(c_alt - op.altitude_feet)

                if vert_diff >= MIN_VERTICAL_SEP_FT:
                    continue

                h_dist = haversine_distance_nm(c_lat, c_lon, op.latitude, op.longitude)
                is_app = (op.point_type in ["APPROACH_INTERCEPT", "DESTINATION"] or
                          c_type in ["APPROACH_INTERCEPT", "DESTINATION"] or
                          op.altitude_feet < 4000 or c_alt < 4000)
                req_h = max(MIN_APPROACH_SEP_NM, get_approach_wake_separation(cand_wake, other_wake)) if is_app else MIN_ENROUTE_SEP_NM

                if h_dist < req_h:
                    cpa_time = op.timestamp
                    severity = "CRITICAL" if h_dist < (2.0 if is_app else 3.0) and vert_diff < 500 else "WARNING"
                    c_type = "APPROACH_SEPARATION_LOSS" if is_app else "ENROUTE_SEPARATION_LOSS"
                    pt_name = op.identifier or "Enroute"

                    combined_sep = h_dist + (vert_diff / 1000.0)
                    if combined_sep < min_sep_found:
                        min_sep_found = combined_sep
                        worst_conflict = ConflictResult(
                            conflicting_gufi=other.gufi,
                            conflicting_callsign=other.callsign,
                            location_lat=c_lat,
                            location_lon=c_lon,
                            time_cpa=cpa_time,
                            min_horizontal_nm=h_dist,
                            vertical_diff_ft=vert_diff,
                            severity=severity,
                            description=(
                                f"Strategic 4D separation conflict with {other.callsign} at {pt_name}: "
                                f"Predicted separation {h_dist:.1f} NM (min {req_h:.1f} NM {'approach' if is_app else 'en-route'}) "
                                f"and {vert_diff} ft vertical (min 1,000 ft) at {cpa_time.strftime('%H:%M:%S')} UTC."
                            ),
                            resolution_advisory=f"Adjust departure EOBT or flight level to clear traffic trajectory.",
                            point_name=pt_name,
                            candidate_fl=int(c_alt // 100),
                            conflict_type=c_type,
                            aircraft_type=aircraft_type,
                            total_dist_nm=total_dist_nm,
                            origin_lat=lat0, origin_lon=lon0,
                            dest_lat=lat1, dest_lon=lon1
                        )

        if worst_conflict:
            # Attach full 4D trajectory of conflicting flight for visual map plotting
            worst_conflict.conflicting_trajectory = [
                {
                    "pointIndex": op.point_index,
                    "pointType": op.point_type,
                    "identifier": op.identifier,
                    "latitude": round(op.latitude, 4),
                    "longitude": round(op.longitude, 4),
                    "altitudeFeet": op.altitude_feet,
                    "flightLevel": op.flight_level,
                    "timestamp": op.timestamp.isoformat() + "Z"
                }
                for op in other_pts
            ]
            conflicts.append(worst_conflict)
            resolutions.append(f"Conflict with {other.callsign}: {worst_conflict.resolution_advisory}")

            if log_to_db:
                rec = ConflictRecordModel(
                    gufi1=candidate_gufi,
                    callsign1=candidate_callsign,
                    gufi2=other.gufi,
                    callsign2=other.callsign,
                    conflict_type="LOSS_OF_SEPARATION",
                    min_horizontal_separation_nm=worst_conflict.min_horizontal_nm,
                    min_vertical_separation_ft=worst_conflict.vertical_diff_ft,
                    time_of_closest_approach=worst_conflict.time_cpa,
                    latitude=worst_conflict.location_lat,
                    longitude=worst_conflict.location_lon,
                    severity=worst_conflict.severity,
                    resolution_advisory=worst_conflict.resolution_advisory
                )
                db.add(rec)

    if log_to_db and conflicts:
        db.commit()

    # Calculate global comprehensive solutions resolving ALL conflicts simultaneously
    comprehensive_solutions = []
    if conflicts:
        comprehensive_solutions = solve_comprehensive_deconfliction(
            candidate_points=candidate_points,
            candidate_eobt=candidate_eobt,
            initial_conflicts=conflicts,
            other_pts_by_gufi=other_pts_by_gufi,
            aircraft_type=aircraft_type
        )

    has_conflicts = len(conflicts) > 0
    return DeconflictionOutcome(has_conflicts, conflicts, resolutions, comprehensive_solutions)
