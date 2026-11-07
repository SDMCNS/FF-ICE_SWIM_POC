"""
Airport Runway Slot Management & ICAO Wake Turbulence Spacing Engine.
Enforces:
  1. ICAO Doc 4444 Chapter 5 Section 5.8 Departure Runway Wake Intervals:
     - Heavy -> Heavy: 120s (2 min)
     - Heavy -> Medium: 120s (2 min)
     - Heavy -> Light: 180s (3 min)
     - Medium -> Light: 120s (2 min)
     - Same category (M->M, L->L): 90s (1.5 min runway occupancy)
  2. ICAO Doc 4444 Chapter 8 Approach Distance Wake Separation:
     - Heavy -> Heavy: 4.0 NM
     - Heavy -> Medium: 5.0 NM
     - Heavy -> Light: 6.0 NM
     - Medium -> Heavy/Medium: 3.0 NM
     - Medium -> Light: 5.0 NM
     - Light -> Any: 3.0 NM
  3. Ground Slot Availability & Deconfliction:
     - Partitions airport operational day into 5-minute runway slot bins.
     - Detects occupied vs available slots against active database plans.
     - Prevents double-booking and restricts candidate selection to open slots.
"""
from datetime import datetime, timedelta, timezone, date
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session
from .database import FlightPlanModel
from .config_loader import (
    get_aircraft_perf,
    get_aircraft_wake_category,
    get_departure_wake_interval as _get_dep_interval,
    get_approach_wake_separation as _get_app_sep,
    get_airport_operations,
    get_airport_runway_mode,
    is_parallel_segregated_airport,
    get_airport_taxi_out_minutes,
    get_airport_taxi_in_minutes,
    get_airport_mixed_mode_occupancy_buffer,
    get_runway_physical_strip_id,
    get_airport_physical_strips
)

# Alias for backwards compatibility
get_wake_category = get_aircraft_wake_category

class _DynamicDepWakeDict(dict):
    def __getitem__(self, key):
        return get_departure_wake_interval(key[0], key[1])
    def get(self, key, default=90):
        return get_departure_wake_interval(key[0], key[1])

class _DynamicAppWakeDict(dict):
    def __getitem__(self, key):
        return get_approach_wake_separation(key[0], key[1])
    def get(self, key, default=3.0):
        return get_approach_wake_separation(key[0], key[1])

DEPARTURE_WAKE_INTERVAL_SEC = _DynamicDepWakeDict()
APPROACH_WAKE_SEPARATION_NM = _DynamicAppWakeDict()

def get_departure_wake_interval(lead_wake: str, trail_wake: str) -> int:
    """Returns minimum departure spacing in seconds between two aircraft on the same runway from JSON config."""
    return _get_dep_interval(lead_wake, trail_wake)

def get_approach_wake_separation(lead_wake: str, trail_wake: str) -> float:
    """Returns minimum horizontal distance in NM between two aircraft on final approach from JSON config."""
    return _get_app_sep(lead_wake, trail_wake)

def get_airport_slots(
    icao: str,
    target_date: date,
    slot_type: str = "DEPARTURE", # DEPARTURE or ARRIVAL
    db: Optional[Session] = None,
    candidate_ac_type: str = "A320",
    start_hour: int = 5,
    end_hour: int = 23,
    interval_minutes: int = 5,
    runway: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluates airport runway capacity and returns a comprehensive slot schedule
    categorized by AVAILABLE vs OCCUPIED status for the requested date and aerodrome.
    Applies ICAO Doc 4444 & Doc 9643 (SOIR) rules:
      - PARALLEL_SEGREGATED (e.g. EGLL, EIDW, EGCC): Departures and arrivals operate on
        physically separate concrete strips. One runway handles departures and the other
        arrivals, preventing false cross-operation conflicts.
      - MULTIPLE_PARALLEL (e.g. LFPG, KORD, KATL, EHAM): Multiple parallel runway sets
        with dedicated arrival strips and departure strips per complex.
      - MIXED_MODE_SINGLE (e.g. EGKK, EGSS, EINN): Single physical runway requires interleaving
        both arrivals and departures with runway occupancy buffers and wake decay separation.
    """
    icao_clean = icao.strip().upper()
    cand_wake = get_aircraft_wake_category(candidate_ac_type)
    ops_cfg = get_airport_operations(icao_clean)
    op_mode = ops_cfg.get("mode", "MIXED_MODE_SINGLE")
    exot = int(ops_cfg.get("taxiOutMinutes", 10))
    exit_time = int(ops_cfg.get("taxiInMinutes", 6))
    mixed_buffer_sec = int(ops_cfg.get("mixedModeOccupancyBufferSec", 75))

    cand_strip_id = get_runway_physical_strip_id(icao_clean, runway) if runway else None

    # 1. Query relevant database flights for this aerodrome and date
    start_dt = datetime.combine(target_date, datetime.min.time()).replace(hour=start_hour)
    end_dt = datetime.combine(target_date, datetime.min.time()).replace(hour=end_hour, minute=59)

    booked_flights = []
    if db is not None:
        # Determine query scope based on airport runway operational mode:
        # Single runway in mixed mode must interleave BOTH departures and arrivals!
        # Parallel segregated & multi-parallel isolate departures from arrivals onto distinct concrete strips.
        query_departures = (slot_type.upper() == "DEPARTURE") or (op_mode == "MIXED_MODE_SINGLE")
        query_arrivals = (slot_type.upper() == "ARRIVAL") or (op_mode == "MIXED_MODE_SINGLE")

        if query_departures:
            dep_plans = (
                db.query(FlightPlanModel)
                .filter(
                    FlightPlanModel.departure_icao == icao_clean,
                    FlightPlanModel.status.in_(["FILED", "AGREED", "ACTIVE"]),
                    FlightPlanModel.eobt >= start_dt - timedelta(minutes=30),
                    FlightPlanModel.eobt <= end_dt + timedelta(minutes=30)
                )
                .all()
            )
            for p in dep_plans:
                # ETOT is runway departure wheels-off time
                etot = p.etot if p.etot else (p.eobt + timedelta(minutes=p.taxi_out_minutes or exot))
                booked_flights.append({
                    "gufi": p.gufi,
                    "callsign": p.callsign,
                    "aircraftType": p.aircraft_type,
                    "wake": p.wake_turbulence or get_aircraft_wake_category(p.aircraft_type),
                    "time": etot,
                    "eobt": p.eobt,
                    "etot": etot,
                    "flightType": "DEPARTURE",
                    "runway": p.departure_runway,
                    "physicalStrip": get_runway_physical_strip_id(icao_clean, p.departure_runway) if p.departure_runway else None,
                    "route": f"{p.departure_icao} -> {p.arrival_icao}"
                })

        if query_arrivals:
            arr_plans = (
                db.query(FlightPlanModel)
                .filter(
                    FlightPlanModel.arrival_icao == icao_clean,
                    FlightPlanModel.status.in_(["FILED", "AGREED", "ACTIVE"]),
                    FlightPlanModel.eta >= start_dt - timedelta(minutes=30),
                    FlightPlanModel.eta <= end_dt + timedelta(minutes=30)
                )
                .all()
            )
            for p in arr_plans:
                # ELDT is runway touchdown time
                eldt = p.eldt if p.eldt else p.eta
                booked_flights.append({
                    "gufi": p.gufi,
                    "callsign": p.callsign,
                    "aircraftType": p.aircraft_type,
                    "wake": p.wake_turbulence or get_aircraft_wake_category(p.aircraft_type),
                    "time": eldt,
                    "eldt": eldt,
                    "eibt": p.eta,
                    "flightType": "ARRIVAL",
                    "runway": p.arrival_runway,
                    "physicalStrip": get_runway_physical_strip_id(icao_clean, p.arrival_runway) if p.arrival_runway else None,
                    "route": f"{p.departure_icao} -> {p.arrival_icao}"
                })

    # 2. Generate slot bins and test occupancy with wake turbulence separation
    slots = []
    curr = start_dt
    total_slots = 0
    available_count = 0
    occupied_count = 0

    while curr <= end_dt:
        total_slots += 1
        slot_etot = curr
        slot_eobt = curr - timedelta(minutes=exot) if slot_type.upper() == "DEPARTURE" else curr
        slot_time_str = curr.strftime("%H:%M")
        eobt_time_str = slot_eobt.strftime("%H:%M")
        iso_str = curr.isoformat() + "Z"
        eobt_iso = slot_eobt.isoformat() + "Z"

        # Check for conflict against any booked flight
        conflicting_booking = None
        req_sec = 0

        for bf in booked_flights:
            # Physical Concrete Strip Isolation Check:
            # When parallel runways exist, departures and arrivals do NOT use the same strip of concrete.
            # Furthermore, flights on different physical strips (e.g. 27L vs 26R at a multi-parallel airport)
            # never conflict on the ground!
            if op_mode in ["PARALLEL_SEGREGATED", "MULTIPLE_PARALLEL"]:
                # Segregated arrivals vs departures:
                if bf["flightType"] != slot_type.upper():
                    continue
                # Same flight type (e.g. both departures):
                # If specific physical strips are known and differ, they operate on different concrete strips!
                if cand_strip_id and bf.get("physicalStrip") and cand_strip_id != bf["physicalStrip"]:
                    continue

            bf_time = bf["time"]
            time_diff_sec = abs((curr - bf_time).total_seconds())

            # Determine leading vs trailing
            if curr >= bf_time:
                lead_w = bf["wake"]
                trail_w = cand_wake
                is_candidate_trailing = True
            else:
                lead_w = cand_wake
                trail_w = bf["wake"]
                is_candidate_trailing = False

            # Calculate separation required depending on operation types
            if slot_type.upper() == "DEPARTURE" and bf["flightType"] == "DEPARTURE":
                sep_sec = get_departure_wake_interval(lead_w, trail_w)
            elif slot_type.upper() == "ARRIVAL" and bf["flightType"] == "ARRIVAL":
                req_nm = get_approach_wake_separation(lead_w, trail_w)
                sep_sec = int((req_nm / 140.0) * 3600.0)
            else:
                # Interleaved operations on single runway (MIXED_MODE_SINGLE)
                # Departure vs Arrival or Arrival vs Departure on same physical strip
                base_buffer = mixed_buffer_sec
                wake_penalty = 30 if (lead_w in ["H", "J"]) else 0
                sep_sec = base_buffer + wake_penalty

            if time_diff_sec < sep_sec:
                conflicting_booking = bf
                req_sec = sep_sec
                break

        if conflicting_booking:
            occupied_count += 1
            op_label = "Interleaved Arrival" if conflicting_booking["flightType"] == "ARRIVAL" and slot_type.upper() == "DEPARTURE" else \
                       "Interleaved Departure" if conflicting_booking["flightType"] == "DEPARTURE" and slot_type.upper() == "ARRIVAL" else \
                       "Departure" if conflicting_booking["flightType"] == "DEPARTURE" else "Arrival"
            reason_str = (
                f"Occupied by {op_label} {conflicting_booking['callsign']} ({conflicting_booking['aircraftType']} / "
                f"Wake {conflicting_booking['wake']}) at {conflicting_booking['time'].strftime('%H:%M')} UTC "
                f"[{op_mode}]"
            )

            slots.append({
                "slot_id": f"{icao_clean}_{slot_time_str.replace(':', '')}",
                "slotTime": slot_time_str,
                "slotTimeEtot": slot_time_str,
                "slotTimeEobt": eobt_time_str,
                "label": slot_time_str,
                "timestamp": iso_str,
                "startTime": iso_str,
                "endTime": (curr + timedelta(minutes=interval_minutes)).isoformat() + "Z",
                "etot": iso_str,
                "eobt": eobt_iso,
                "exotMinutes": exot,
                "status": "OCCUPIED",
                "isAvailable": False,
                "bookedCallsign": conflicting_booking["callsign"],
                "allocatedCallsign": conflicting_booking["callsign"],
                "bookedAircraft": conflicting_booking["aircraftType"],
                "allocatedAircraftType": conflicting_booking["aircraftType"],
                "bookedWake": conflicting_booking["wake"],
                "allocatedWakeCategory": conflicting_booking["wake"],
                "bookedRoute": conflicting_booking["route"],
                "bookedRunway": conflicting_booking["runway"] or "Active",
                "runwayDesignator": conflicting_booking["runway"] or "Active",
                "operationalMode": op_mode,
                "wakeSeparationRequiredSec": req_sec,
                "reason": reason_str,
                "conflictReason": reason_str
            })
        else:
            available_count += 1
            slots.append({
                "slot_id": f"{icao_clean}_{slot_time_str.replace(':', '')}",
                "slotTime": slot_time_str,
                "slotTimeEtot": slot_time_str,
                "slotTimeEobt": eobt_time_str,
                "label": slot_time_str,
                "timestamp": iso_str,
                "startTime": iso_str,
                "endTime": (curr + timedelta(minutes=interval_minutes)).isoformat() + "Z",
                "etot": iso_str,
                "eobt": eobt_iso,
                "exotMinutes": exot,
                "status": "AVAILABLE",
                "isAvailable": True,
                "bookedCallsign": None,
                "allocatedCallsign": None,
                "bookedAircraft": None,
                "allocatedAircraftType": None,
                "bookedWake": None,
                "allocatedWakeCategory": None,
                "bookedRoute": None,
                "bookedRunway": None,
                "runwayDesignator": None,
                "operationalMode": op_mode,
                "wakeSeparationRequiredSec": 0,
                "reason": f"Runway slot open for allocation ({op_mode})",
                "conflictReason": None
            })

        curr += timedelta(minutes=interval_minutes)

    return {
        "airport": icao_clean,
        "aerodrome": icao_clean,
        "date": target_date.isoformat(),
        "slotType": slot_type.upper(),
        "candidateAircraftType": candidate_ac_type,
        "candidateWakeCategory": cand_wake,
        "operationalMode": op_mode,
        "isParallelSegregated": op_mode in ["PARALLEL_SEGREGATED", "MULTIPLE_PARALLEL"],
        "taxiOutMinutes": exot,
        "taxiInMinutes": exit_time,
        "totalSlots": total_slots,
        "availableCount": available_count,
        "occupiedCount": occupied_count,
        "summary": {
            "totalSlots": total_slots,
            "available": available_count,
            "occupied": occupied_count,
            "capacityUtilization": round((occupied_count / max(1, total_slots)) * 100, 1),
            "operationalMode": op_mode
        },
        "slots": slots
    }

class AvailableSlotResult:
    def __init__(self, slot_dt: datetime, label: str, slot_dict: Dict[str, Any], exot_minutes: int = 10, op_mode: str = "MIXED_MODE_SINGLE"):
        self.time = slot_dt # Runway ETOT
        self.etot = slot_dt
        self.exot_minutes = exot_minutes
        self.eobt = slot_dt - timedelta(minutes=exot_minutes) # Calculated backwards from ETOT
        self.label = label
        self.status = "AVAILABLE"
        self.slot = slot_dict
        self.operational_mode = op_mode

    def to_dict(self) -> Dict[str, Any]:
        return {
            "time": self.time.isoformat() + "Z",
            "etot": self.etot.isoformat() + "Z",
            "eobt": self.eobt.isoformat() + "Z",
            "slotTimeEtot": self.etot.isoformat() + "Z",
            "slotTimeEobt": self.eobt.isoformat() + "Z",
            "label": self.label,
            "status": self.status,
            "exotMinutes": self.exot_minutes,
            "operationalMode": self.operational_mode,
            "slot": self.slot
        }

    def __getitem__(self, item: str):
        return self.to_dict()[item]

    def isoformat(self) -> str:
        return self.time.isoformat()

    def __str__(self) -> str:
        return self.time.isoformat()

def find_next_available_slot(
    icao: Any = "EGLL",
    desired_dt: Any = None,
    slot_type: str = "DEPARTURE",
    db: Optional[Session] = None,
    candidate_ac_type: str = "A320",
    *args,
    **kwargs
) -> Optional[AvailableSlotResult]:
    """
    Finds the nearest conflict-free runway slot at or immediately after desired_dt.
    Accepts desired time as either EOBT (stand pushback) or ETOT (wheels-off).
    Calculates backwards to off-stand time using airport EXOT.
    """
    if desired_dt is None:
        desired_dt = datetime.now(timezone.utc)

    if not isinstance(icao, str):
        actual_db = icao
        actual_icao = str(desired_dt)
        actual_dt = args[0] if args else kwargs.get("desired_dt", datetime.now(timezone.utc))
    else:
        actual_icao = icao
        actual_dt = desired_dt
        actual_db = db or kwargs.get("db")

    # Extract keyword aliases
    target_runway = kwargs.get("runway")
    if "operation" in kwargs:
        slot_type = kwargs["operation"]
    if "aircraft_type" in kwargs:
        candidate_ac_type = kwargs["aircraft_type"]
    if "desired_time" in kwargs:
        actual_dt = kwargs["desired_time"]

    ops_cfg = get_airport_operations(actual_icao)
    exot = int(ops_cfg.get("taxiOutMinutes", 10))
    op_mode = ops_cfg.get("mode", "MIXED_MODE_SINGLE")

    # If desired_dt was an EOBT, the desired runway time (ETOT) is EOBT + EXOT
    # Check if kwargs specified whether desired_dt was explicitly ETOT
    is_already_etot = kwargs.get("is_etot", False)
    search_dt = actual_dt if is_already_etot else (actual_dt + timedelta(minutes=exot))

    target_date = search_dt.date() if isinstance(search_dt, datetime) else date.today()
    desired_hour = search_dt.hour if isinstance(search_dt, datetime) else 12

    slot_info = get_airport_slots(
        icao=actual_icao,
        target_date=target_date,
        slot_type=slot_type,
        db=actual_db,
        candidate_ac_type=candidate_ac_type,
        start_hour=max(0, desired_hour - 1),
        end_hour=min(23, desired_hour + 4),
        interval_minutes=5,
        runway=target_runway
    )

    for s in slot_info["slots"]:
        s_dt = datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00")).replace(tzinfo=None)
        cmp_dt = search_dt.replace(tzinfo=None) if isinstance(search_dt, datetime) and search_dt.tzinfo else search_dt
        if s_dt >= cmp_dt and s["isAvailable"]:
            return AvailableSlotResult(s_dt, s["label"], s, exot_minutes=exot, op_mode=op_mode)

    return None
