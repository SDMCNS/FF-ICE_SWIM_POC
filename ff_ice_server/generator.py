"""
Core Traffic Generation Engine for Realistic Commercial UK & Irish Flights.
"""
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any
from sqlalchemy.orm import Session
import json

from .database import FlightPlanModel, TrajectoryPointModel
from .aero_data import AeroDataStore, initial_bearing_deg
from .trajectory import calculate_4d_trajectory, AIRCRAFT_PERF
from .fixm_engine import serialize_to_fixm_xml, generate_gufi
from .deconfliction import deconflict_trajectory

ROUTE_CORRIDORS = [
    ("EGLL", "EIDW", ["LIPGO"]),
    ("EIDW", "EGLL", ["LIPGO"]),
    ("EGKK", "EIDW", ["LIPGO"]),
    ("EIDW", "EGKK", ["LIPGO"]),
    ("EGCC", "EIDW", ["LIPGO"]),
    ("EIDW", "EGCC", ["LIPGO"]),
    ("EGPH", "EIDW", ["SUROX"]),
    ("EIDW", "EGPH", ["SUROX"]),
    ("EGPF", "EIDW", ["SUROX"]),
    ("EIDW", "EGPF", ["SUROX"]),
    ("EGBB", "EIDW", ["LIPGO"]),
    ("EIDW", "EGBB", ["LIPGO"]),
    ("EGAA", "EGLL", ["SUROX"]),
    ("EGLL", "EGAA", ["SUROX"]),
    ("EICK", "EGLL", ["LIPGO"]),
    ("EGLL", "EICK", ["LIPGO"]),
    ("EINN", "EGKK", ["LIPGO"]),
    ("EGKK", "EINN", ["LIPGO"]),
    ("EGLL", "EGPH", ["TLA"]),
    ("EGPH", "EGLL", ["TLA"]),
    ("EGLL", "EGCC", ["WAL"]),
    ("EGCC", "EGLL", ["WAL"]),
]

AIRLINES = [
    ("EIN", "Aer Lingus", ["A320", "A321", "AT76"]),
    ("BAW", "British Airways", ["A320", "A321", "E190", "B77W"]),
    ("RYR", "Ryanair", ["B738", "A320"]),
    ("EZY", "easyJet", ["A320", "A321"]),
    ("LOG", "Loganair", ["AT76", "DH8D", "E190"])
]

def generate_realistic_traffic(count: int, hours: float, db: Session, store: AeroDataStore) -> List[Dict[str, Any]]:
    firs_list = list(store.firs.values())
    base_time = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=10)
    window_seconds = int(hours * 3600)
    generated_plans = []

    for i in range(count):
        dep_icao, arr_icao, wp_names = random.choice(ROUTE_CORRIDORS)
        dep_aero = store.airports.get(dep_icao)
        arr_aero = store.airports.get(arr_icao)
        if not dep_aero or not arr_aero: continue

        waypoints = [store.waypoints[w] for w in wp_names if w in store.waypoints]
        airline_code, airline_name, ac_options = random.choice(AIRLINES)
        callsign = f"{airline_code}{random.randint(101, 999)}"
        ac_type = random.choice(ac_options)
        ac_perf = AIRCRAFT_PERF[ac_type]

        brg = initial_bearing_deg(dep_aero["latitude"], dep_aero["longitude"], arr_aero["latitude"], arr_aero["longitude"])
        is_east = (0 <= brg < 180)

        # Distance estimation to cap FL
        dist_est = 250.0
        if "EGCC" in (dep_icao, arr_icao): dist_est = 140.0
        elif "EICK" in (dep_icao, arr_icao): dist_est = 310.0

        if dist_est < 160 or ac_perf["ceiling"] < 260:
            fl_choices = [180, 200, 220, 240] if not is_east else [170, 190, 210, 230]
        else:
            fl_choices = [260, 280, 300, 320, 340, 360] if not is_east else [270, 290, 310, 330, 350, 370]

        valid_fls = [f for f in fl_choices if f <= ac_perf["ceiling"]]
        if not valid_fls:
            valid_fls = [180, 200, 220] if not is_east else [170, 190, 210]
        cruise_fl = random.choice(valid_fls)
        offset_sec = random.randint(0, window_seconds)
        eobt_dt = base_time + timedelta(seconds=offset_sec)

        traj = calculate_4d_trajectory(
            dep_airport=dep_aero,
            arr_airport=arr_aero,
            waypoints=waypoints,
            aircraft_type=ac_type,
            requested_fl=cruise_fl,
            eobt_dt=eobt_dt,
            firs=firs_list
        )

        eta_dt = eobt_dt + timedelta(minutes=traj["totalFlightTimeMinutes"])
        gufi = generate_gufi()

        has_conflicts, conflicts, resolutions = deconflict_trajectory(
            candidate_gufi=gufi,
            candidate_callsign=callsign,
            candidate_points=traj["points"],
            candidate_eobt=eobt_dt,
            candidate_eta=eta_dt,
            db=db,
            log_to_db=True,
            aircraft_type=ac_type
        )

        plan_dict = {
            "gufi": gufi,
            "status": "FILED",
            "messageType": "FILING",
            "filingTime": datetime.now(timezone.utc).isoformat() + "Z",
            "flightIdentification": {
                "aircraftIdentification": callsign,
                "aircraftRegistration": f"{'EI' if dep_aero['country'] == 'IE' else 'G'}-{chr(random.randint(65, 90))}{chr(random.randint(65, 90))}{chr(random.randint(65, 90))}"
            },
            "aircraft": {
                "aircraftType": ac_type,
                "wakeTurbulence": ac_perf["wake"],
                "capabilities": {"standardEquipment": ac_perf["defaultEquipment"]}
            },
            "departure": {
                "aerodrome": dep_icao,
                "elevationFeet": dep_aero["elevationFeet"],
                "estimatedOffBlockTime": eobt_dt.isoformat() + "Z"
            },
            "arrival": {
                "aerodrome": arr_icao,
                "elevationFeet": arr_aero["elevationFeet"],
                "estimatedTimeOfArrival": eta_dt.isoformat() + "Z"
            },
            "enRoute": {
                "cruisingLevel": f"F{cruise_fl}",
                "cruisingSpeed": f"N0{ac_perf['cruiseTas']}",
                "routeString": f"{dep_icao} {' '.join(wp_names)} {arr_icao}"
            },
            "trajectory": {
                "points4D": traj["points"],
                "totalDistanceNm": traj["totalDistanceNm"],
                "totalFlightTimeMinutes": traj["totalFlightTimeMinutes"]
            }
        }

        xml_str = serialize_to_fixm_xml(plan_dict)

        db_plan = FlightPlanModel(
            gufi=gufi,
            callsign=callsign,
            registration=plan_dict["flightIdentification"]["aircraftRegistration"],
            status="FILED",
            message_type="FILING",
            departure_icao=dep_icao,
            departure_elevation_ft=dep_aero["elevationFeet"],
            eobt=eobt_dt,
            arrival_icao=arr_icao,
            arrival_elevation_ft=arr_aero["elevationFeet"],
            eta=eta_dt,
            aircraft_type=ac_type,
            wake_turbulence=ac_perf["wake"],
            equipment=ac_perf["defaultEquipment"],
            cruising_level=f"F{cruise_fl}",
            cruising_speed=f"N0{ac_perf['cruiseTas']}",
            route_string=plan_dict["enRoute"]["routeString"],
            total_distance_nm=traj["totalDistanceNm"],
            total_flight_time_minutes=traj["totalFlightTimeMinutes"],
            fixm_json=json.dumps(plan_dict),
            fixm_xml=xml_str
        )
        db.add(db_plan)

        for idx, pt in enumerate(traj["points"]):
            c = pt["coordinates"]
            t_str = pt["estimatedTimestamp"].replace("Z", "")
            pt_dt = datetime.fromisoformat(t_str)
            db_pt = TrajectoryPointModel(
                gufi=gufi,
                point_index=idx,
                point_type=pt["pointType"],
                identifier=pt["identifier"],
                latitude=c["latitude"],
                longitude=c["longitude"],
                altitude_feet=pt["altitudeFeet"],
                flight_level=pt["flightLevel"],
                cumulative_distance_nm=pt["cumulativeDistanceNm"],
                ground_speed_knots=pt["groundSpeedKnots"],
                timestamp=pt_dt,
                airspace=pt.get("associatedAirspace")
            )
            db.add(db_pt)

        db.commit()
        generated_plans.append(plan_dict)

    return generated_plans
