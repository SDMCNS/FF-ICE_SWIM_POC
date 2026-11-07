"""
SWIM-Compliant FF-ICE REST API Server in Python (FastAPI).
Integrates SQLite Database Persistence, 4D Strategic Deconfliction, and Static Front-End Hosting.
"""
import os
import json
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone, date, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, Response, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .database import init_db, FlightPlanModel, TrajectoryPointModel, ConflictRecordModel
from .aero_data import AeroDataStore
from .trajectory import calculate_4d_trajectory, AIRCRAFT_PERF
from .deconfliction import deconflict_trajectory
from .fixm_engine import serialize_to_fixm_xml, parse_fixm_xml, generate_gufi
from .generator import generate_realistic_traffic
from .weather import get_metar, get_taf, determine_active_runway
from .autofill import autofill_route
from .airspace_graph import get_airspace_graph, reset_airspace_graph
from .slots import get_airport_slots, find_next_available_slot
from .gufi_registry import (
    allocate_central_gufi,
    verify_central_gufi,
    commit_central_gufi,
    release_central_gufi,
    list_central_gufis,
    ISSUING_AUTHORITY,
    CENTRAL_REGISTRY_URN
)
from .config_loader import (
    reload_configuration,
    get_aircraft_database,
    get_airway_routes,
    save_custom_override,
    get_departure_wake_interval,
    get_approach_wake_separation,
    get_airport_operations,
    get_airport_runway_mode,
    is_parallel_segregated_airport,
    get_airport_taxi_out_minutes,
    get_airport_taxi_in_minutes,
    get_airport_mixed_mode_occupancy_buffer,
    get_runway_physical_strip_id,
    get_airport_physical_strips
)
from .plan_lifecycle import (
    determine_operational_status,
    is_plan_active,
    sweep_expired_flight_plans,
    background_sweeper_loop,
    ETA_BUFFER_MINUTES,
    EOBT_EXPIRED_MINUTES
)

# Initialize Database and AeroStore
DB_PATH = os.environ.get("FF_ICE_DB", "ff_ice.db")
engine, SessionLocal = init_db(DB_PATH)
aero_store = AeroDataStore(base_dir=os.path.abspath("."))

_sweeper_stop_event = asyncio.Event()
_sweeper_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI Lifespan Context Manager.
    Starts background sweeper task on startup to prune old plans from active listings.
    Gracefully stops the sweeper task on shutdown.
    """
    global _sweeper_task
    try:
        with SessionLocal() as db:
            sweep_expired_flight_plans(db)
    except Exception as e:
        print(f"[Lifespan] Initial plan sweep failed: {e}")

    _sweeper_stop_event.clear()
    _sweeper_task = asyncio.create_task(
        background_sweeper_loop(SessionLocal, _sweeper_stop_event, interval_seconds=30)
    )
    try:
        yield
    finally:
        _sweeper_stop_event.set()
        if _sweeper_task:
            try:
                await asyncio.wait_for(_sweeper_task, timeout=3.0)
            except Exception:
                pass

app = FastAPI(
    title="SWIM FF-ICE Flight Planning & 4D Deconfliction Information Service",
    version="2.0.0",
    description="ICAO Doc 9965 & FIXM v4.2+ compliant System-Wide Information Management (SWIM) flight planning, 4D trajectory advisory, and strategic deconfliction service with SQLite database persistence.",
    lifespan=lifespan
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(HTTPException)
async def swim_rfc7807_exception_handler(request: Request, exc: HTTPException):
    """
    SWIM Yellow Profile RFC 7807 Problem Details Error Handler.
    Returns application/problem+json formatted errors.
    """
    accept = request.headers.get("accept", "")
    detail = exc.detail
    title = "HTTP Error"
    detail_str = str(detail)
    extensions = {}

    if isinstance(detail, dict):
        title = detail.get("error") or detail.get("status") or "Operation Failed"
        detail_str = detail.get("message") or "Airspace operation conflict or validation failure."
        extensions = detail

    problem_body = {
        "type": f"urn:swim:error:{exc.status_code}",
        "title": title,
        "status": exc.status_code,
        "detail": detail_str,
        "instance": str(request.url.path),
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
    }
    if extensions:
        problem_body["extensions"] = extensions

    return JSONResponse(
        status_code=exc.status_code,
        content=problem_body,
        media_type="application/problem+json"
    )

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/api/v1/health", summary="Health Check")
def health_check():
    return {
        "status": "HEALTHY",
        "service": "SWIM FF-ICE Flight Planning & 4D Trajectory Information Service",
        "version": "2.0.0"
    }

# -------------------------------------------------------------
# SWIM Yellow Profile Service Definition & Monitoring Endpoints
# -------------------------------------------------------------
@app.get("/api/v1/swim/service-description", summary="SWIM Yellow Profile Service Description Document (SDD)")
def get_swim_service_description(request: Request):
    """
    Returns the official Service Description Document (SDD) for this service
    in compliance with Eurocontrol SWIM Yellow Profile Technical Infrastructure (TI)
    specifications and ICAO Doc 10039 (Manual on SWIM Concept).
    """
    base_url = str(request.base_url).rstrip("/")
    return {
        "serviceIdentification": {
            "serviceName": "FF-ICE 4D Flight Planning & Strategic Deconfliction Information Service",
            "serviceUrn": "urn:swim:service:ffice:flight-planning:v1",
            "serviceVersion": "2.0.0",
            "serviceProvider": "SWIM AIRSPACE DEMO PROVIDER (IAA/NATS)",
            "serviceDescription": "Authoritative SWIM Yellow Profile compliant service for filing, 4D trajectory calculation, runway slot allocation with wake turbulence separation, and 4D strategic deconfliction.",
            "conformanceProfile": "EUROCONTROL SWIM Yellow Profile (TI-Profile Yellow v2.0)",
            "standardsCompliance": [
                "ICAO Doc 9965 (Manual on FF-ICE/R)",
                "ICAO Doc 10039 (Manual on System-Wide Information Management)",
                "ICAO Doc 9643 (Manual on Simultaneous Operations on Parallel or Near-Parallel Instrument Runways - SOIR)",
                "ICAO Doc 4444 (PANS-ATM Wake Turbulence & Separation Standards)",
                "FIXM v4.2+ / iFIXM Core Schema",
                "RFC 7807 (Problem Details for HTTP APIs)"
            ]
        },
        "serviceTechnicalInterface": {
            "transportProtocol": "HTTP/1.1, HTTP/2 over TLS 1.3",
            "serviceType": "RESTful Web Service",
            "apiSpecification": f"{base_url}/openapi.json",
            "interactiveDocs": f"{base_url}/docs",
            "supportedPayloadFormats": [
                "application/json",
                "application/vnd.fixm+xml",
                "application/problem+json"
            ],
            "defaultPayloadFormat": "application/json"
        },
        "messageExchangePatterns": [
            {
                "mepName": "Request-Response (IN-OUT)",
                "protocol": "HTTP Synchronous",
                "operations": [
                    "POST /api/v1/trajectory/calculate",
                    "POST /api/v1/ffice/plans",
                    "GET /api/v1/ffice/plans/{gufi}",
                    "GET /api/v1/airports/{icao}/slots",
                    "POST /api/v1/registry/gufi/allocate",
                    "GET /api/v1/registry/gufi/{gufi}/verify"
                ]
            },
            {
                "mepName": "Publish-Subscribe (Notification/Event-Driven)",
                "protocol": "WebSocket / SSE (Roadmap Target for SWIM Blue Profile bridge)",
                "topics": [
                    "urn:swim:topic:trajectory:conflict-alert",
                    "urn:swim:topic:slot:occupancy-update",
                    "urn:swim:topic:gufi:status-change"
                ]
            }
        ],
        "qualityOfService": {
            "serviceLevelAgreement": {
                "availability": "99.95%",
                "meanTimeToRespondMs": 120,
                "p95LatencyMs": 350,
                "maxPayloadSizeKb": 2048
            },
            "securityProfile": {
                "authentication": "SWIM PKI Mutual TLS (mTLS) or OAuth2 Bearer Token in federated mesh; Demo mode permits open REST calls.",
                "transportSecurity": "HTTPS / TLS 1.2+ required in production."
            }
        },
        "centralRegistryFederation": {
            "status": "DEMONSTRATION_PLACEHOLDER",
            "note": "A central registry service is currently emulated locally to prevent GUFI collisions. In full European/Global deployment, this calls the external Central Register via SWIM registry broker.",
            "endpoints": {
                "allocate": f"{base_url}/api/v1/registry/gufi/allocate",
                "verify": f"{base_url}/api/v1/registry/gufi/{{gufi}}/verify",
                "list": f"{base_url}/api/v1/registry/gufi"
            }
        }
    }

@app.get("/api/v1/swim/health", summary="SWIM Yellow Profile Standard Health Status")
def get_swim_health(db: Session = Depends(get_db)):
    """
    Standard Yellow Profile Health and Monitoring interface.
    """
    db_ok = True
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    return {
        "status": "HEALTHY" if db_ok else "DEGRADED",
        "service": "SWIM FF-ICE Flight Planning Information Service",
        "serviceUrn": "urn:swim:service:ffice:flight-planning:v1",
        "yellowProfileCompliant": True,
        "databaseConnected": db_ok,
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "version": "2.0.0"
    }

@app.get("/api/v1/swim/status", summary="SWIM Yellow Profile Operational Status")
def get_swim_status(db: Session = Depends(get_db)):
    """
    Operational metrics and capability status for SWIM consumers.
    """
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now_utc - timedelta(minutes=ETA_BUFFER_MINUTES)

    total_plans = db.query(FlightPlanModel).count()
    active_plans = db.query(FlightPlanModel).filter(
        FlightPlanModel.status.in_(["FILED", "AGREED", "ACTIVE"]),
        FlightPlanModel.eta >= cutoff
    ).count()
    upcoming_plans = db.query(FlightPlanModel).filter(
        FlightPlanModel.status.in_(["FILED", "AGREED", "ACTIVE"]),
        FlightPlanModel.eobt > now_utc
    ).count()
    inflight_plans = db.query(FlightPlanModel).filter(
        FlightPlanModel.status.in_(["FILED", "AGREED", "ACTIVE"]),
        FlightPlanModel.eobt <= now_utc,
        FlightPlanModel.eta >= cutoff
    ).count()
    completed_plans = db.query(FlightPlanModel).filter(
        FlightPlanModel.status == "COMPLETED"
    ).count()
    expired_plans = db.query(FlightPlanModel).filter(
        FlightPlanModel.status == "EXPIRED"
    ).count()
    conflicts_logged = db.query(ConflictRecordModel).count()
    ops = get_airport_operations()
    gufis = list_central_gufis(limit=1000)

    return {
        "serviceUrn": "urn:swim:service:ffice:flight-planning:v1",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "statistics": {
            "totalPlans": total_plans,
            "activeFiledPlans": active_plans,
            "upcomingPlans": upcoming_plans,
            "inFlightPlans": inflight_plans,
            "completedPlans": completed_plans,
            "expiredPlans": expired_plans,
            "conflictsLogged": conflicts_logged,
            "centrallyAllocatedGufis": len(gufis)
        },
        "lifecyclePolicy": {
            "etaBufferMinutes": ETA_BUFFER_MINUTES,
            "eobtExpiredMinutes": EOBT_EXPIRED_MINUTES,
            "backgroundSweeperRunning": True
        },
        "airportsConfigured": len(ops),
        "runwayModesSupported": [
            "PARALLEL_SEGREGATED",
            "MIXED_MODE_SINGLE",
            "MULTIPLE_PARALLEL"
        ],
        "yellowProfileTI": {
            "contentNegotiation": True,
            "rfc7807ProblemDetails": True,
            "fixmVersions": ["4.2", "4.3", "iFIXM-2.0"]
        }
    }

# -------------------------------------------------------------
# Central GUFI Registry (ICAO Doc 9965 Central Register Placeholder)
# -------------------------------------------------------------
@app.post("/api/v1/registry/gufi/allocate", summary="Allocate Central GUFI (ICAO Doc 9965 Central Register)")
async def allocate_gufi_endpoint(request: Request):
    """
    SWIM Yellow Profile Central GUFI Allocation Service.
    Centrally coordinates and reserves an authoritative GUFI to prevent collisions
    across multi-client dispatchers prior to flight plan filing.
    """
    body = await request.json()
    callsign = body.get("callsign", "UNTITLED")
    dep = body.get("departureIcao", "")
    arr = body.get("arrivalIcao", "")
    eobt = body.get("estimatedOffBlockTime") or body.get("eobt")
    client_id = body.get("clientId", "SWIM-WEB-CLIENT")
    originating_ansp = body.get("originatingAnsp", "IAA/NATS")

    record = allocate_central_gufi(
        callsign=callsign,
        departure_icao=dep,
        arrival_icao=arr,
        eobt=eobt,
        client_id=client_id,
        originating_ansp=originating_ansp
    )
    return record

@app.get("/api/v1/registry/gufi/{gufi}/verify", summary="Verify Registered Central GUFI")
def verify_gufi_endpoint(gufi: str):
    """
    Verifies that a GUFI is recognized and validated by the Central Flight Plan Registry.
    """
    return verify_central_gufi(gufi)

@app.get("/api/v1/registry/gufi", summary="List Centrally Coordinated GUFIs")
def list_gufis_endpoint(limit: int = 100):
    """
    Lists actively allocated and committed GUFIs managed by the Central Registry Node.
    """
    return {
        "issuingAuthority": ISSUING_AUTHORITY,
        "centralRegistryUrn": CENTRAL_REGISTRY_URN,
        "isPlaceholder": True,
        "notice": "Demonstration node for ICAO Doc 9965 Central Flight Plan Registry called via SWIM Yellow Profile.",
        "gufis": list_central_gufis(limit)
    }

# -------------------------------------------------------------
# 1. Reference Data Endpoints
# -------------------------------------------------------------
@app.get("/api/v1/airports", summary="Query Aerodromes (UK & Ireland)")
def get_airports(query: str = Query("", description="Search by ICAO or name"), limit: int = 30):
    return aero_store.search_airports(query, limit)

@app.get("/api/v1/waypoints", summary="Query Waypoints (UK & Ireland)")
def get_waypoints(query: str = Query("", description="Search by waypoint code"), limit: int = 30):
    return aero_store.search_waypoints(query, limit)

@app.get("/api/v1/airspace/fir", summary="Get UK & Irish 3D FIR Airspaces")
def get_firs():
    return list(aero_store.firs.values())

@app.get("/api/v1/aircraft", summary="Get Aircraft Performance Profiles")
def get_aircraft():
    return list(AIRCRAFT_PERF.values())

@app.get("/api/v1/config/metadata", summary="Get Configuration Metadata & Loaded Status")
def get_config_metadata():
    return reload_configuration()

@app.get("/api/v1/config/aircraft", summary="List All Configured Aircraft Profiles")
def list_config_aircraft():
    return get_aircraft_database()

@app.post("/api/v1/config/aircraft", summary="Add or Update Aircraft Performance Profile")
async def update_aircraft_config(request: Request):
    data = await request.json()
    icao_type = data.get("icaoType", "").strip().upper()
    if not icao_type:
        raise HTTPException(status_code=400, detail="icaoType is required (e.g. 'B789', 'A333').")

    save_custom_override("aircraft", icao_type, data)
    return {
        "status": "SUCCESS",
        "message": f"Aircraft profile '{icao_type}' saved to custom overrides and hot-reloaded successfully.",
        "profile": get_aircraft_database().get(icao_type)
    }

@app.get("/api/v1/config/wake-rules", summary="Get Wake Turbulence Separation Matrix")
def get_wake_rules_endpoint():
    cats = ["H", "M", "L", "J"]
    dep_matrix = {}
    app_matrix = {}
    for lead in cats:
        for trail in cats:
            pair = f"{lead}_{trail}"
            dep_matrix[pair] = get_departure_wake_interval(lead, trail)
            app_matrix[pair] = get_approach_wake_separation(lead, trail)

    return {
        "departureWakeIntervalsSec": dep_matrix,
        "approachWakeSeparationNm": app_matrix
    }

@app.get("/api/v1/config/airways", summary="Get Configured Airway Routes")
def get_airways_config():
    return get_airway_routes()

@app.post("/api/v1/aero/rebuild", summary="Rebuild Aeronautical Database & Navigation Graph")
def rebuild_aeronautical_database(base_dir: Optional[str] = None):
    """
    Dynamically re-scans the airports, Waypoints, routes, and FIR directories,
    re-ingesting all data (location-agnostic across any region or country),
    rebuilding the topological airspace navigation graph, and re-synthesizing
    airport operations and physical runway strip layouts.
    """
    global aero_store
    aero_store.rebuild(base_dir=base_dir)
    graph = reset_airspace_graph(aero_store)
    meta = reload_configuration()

    return {
        "status": "SUCCESS",
        "message": "Aeronautical database, airspace graph, and airport runway operations successfully rebuilt.",
        "airportsCount": len(aero_store.airports),
        "waypointsCount": len(aero_store.waypoints),
        "routesCount": len(aero_store.routes),
        "firsCount": len(aero_store.firs),
        "graphNodesCount": len(graph.nodes) if graph else 0,
        "operationalAirportsCount": len(get_airport_operations()),
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
    }

@app.get("/api/v1/airports/{icao}/runways", summary="Get Airport Physical Concrete Strips & Operational Mode")
def get_airport_runways(icao: str):
    icao_clean = icao.strip().upper()
    ops = get_airport_operations(icao_clean)
    strips = get_airport_physical_strips(icao_clean)
    return {
        "icao": icao_clean,
        "mode": ops.get("mode", "MIXED_MODE_SINGLE"),
        "physicalStrips": strips,
        "westOperations": ops.get("westOperations"),
        "eastOperations": ops.get("eastOperations"),
        "taxiOutMinutes": ops.get("taxiOutMinutes", 10),
        "taxiInMinutes": ops.get("taxiInMinutes", 6)
    }

@app.post("/api/v1/config/reload", summary="Hot-Reload All JSON Configurations")
def reload_config_endpoint():
    global aero_store
    aero_store.rebuild()
    reset_airspace_graph(aero_store)
    meta = reload_configuration()
    return {
        "status": "SUCCESS",
        "message": "All JSON configurations and aeronautical stores reloaded successfully from disk.",
        "metadata": meta
    }

@app.get("/api/v1/weather/metar", summary="Fetch Live NOAA METAR & Active Runway")
def get_weather_metar(icao: str = Query(..., description="4-letter ICAO identifier (e.g. EGLL, EIDW, EINN)")):
    icao_clean = icao.strip().upper()
    airport = aero_store.airports.get(icao_clean)
    metar = get_metar(icao_clean)
    taf = get_taf(icao_clean)
    active_info = determine_active_runway(airport, metar) if airport else None

    return {
        "icao": icao_clean,
        "name": airport.get("name") if airport else icao_clean,
        "country": airport.get("country", "") if airport else "",
        "elevation": airport.get("elevation", 0) if airport else 0,
        "metar": metar,
        "taf": taf,
        "activeRunway": active_info
    }

@app.get("/api/v1/airports/{icao}/slots", summary="Query Aerodrome Runway Slots & Capacity")
def get_slots_endpoint(
    icao: str,
    date_str: Optional[str] = Query(None, alias="date", description="Date YYYY-MM-DD (defaults to today UTC)"),
    slot_type: str = Query("DEPARTURE", alias="slotType"),
    slot_type_alt: Optional[str] = Query(None, alias="type"),
    aircraft_type: str = Query("A320", alias="acType"),
    aircraft_type_alt: Optional[str] = Query(None, alias="aircraftType"),
    start_hour: int = Query(5, alias="startHour"),
    end_hour: int = Query(23, alias="endHour"),
    db: Session = Depends(get_db)
):
    actual_slot_type = slot_type_alt or slot_type or "DEPARTURE"
    actual_ac = aircraft_type_alt or aircraft_type or "A320"
    try:
        target_d = date.fromisoformat(date_str) if date_str else datetime.now(timezone.utc).date()
    except Exception:
        target_d = datetime.now(timezone.utc).date()

    return get_airport_slots(
        icao=icao,
        target_date=target_d,
        slot_type=actual_slot_type,
        db=db,
        candidate_ac_type=actual_ac,
        start_hour=start_hour,
        end_hour=end_hour
    )

@app.get("/api/v1/airports/{icao}/slots/next-available", summary="Find Next Conflict-Free Slot")
def get_next_slot_endpoint(
    icao: str,
    time_str: Optional[str] = Query(None, alias="time"),
    desired_time: Optional[str] = Query(None, alias="desiredTime"),
    slot_type: str = Query("DEPARTURE", alias="slotType"),
    slot_type_alt: Optional[str] = Query(None, alias="type"),
    aircraft_type: str = Query("A320", alias="acType"),
    aircraft_type_alt: Optional[str] = Query(None, alias="aircraftType"),
    db: Session = Depends(get_db)
):
    actual_time = desired_time or time_str or datetime.now(timezone.utc).isoformat()
    actual_slot_type = slot_type_alt or slot_type or "DEPARTURE"
    actual_ac = aircraft_type_alt or aircraft_type or "A320"

    try:
        dt = datetime.fromisoformat(actual_time.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid time format. Use ISO format YYYY-MM-DDTHH:MM:SS")

    next_slot = find_next_available_slot(
        icao=icao,
        desired_dt=dt,
        slot_type=actual_slot_type,
        db=db,
        candidate_ac_type=actual_ac
    )
    next_iso = next_slot.isoformat() if hasattr(next_slot, "isoformat") else str(next_slot) if next_slot else None
    delay_min = None
    if next_slot:
        s_dt = next_slot.time if hasattr(next_slot, "time") else next_slot
        if isinstance(s_dt, datetime):
            if s_dt.tzinfo is None and dt.tzinfo is not None:
                s_dt = s_dt.replace(tzinfo=timezone.utc)
            elif s_dt.tzinfo is not None and dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            delay_min = max(0, int((s_dt - dt).total_seconds() / 60))

    return {
        "aerodrome": icao.upper(),
        "airport": icao.upper(),
        "slotType": actual_slot_type.upper(),
        "requestedTime": actual_time,
        "nextAvailableTime": next_iso,
        "delayMinutes": delay_min,
        "label": getattr(next_slot, "label", ""),
        "slot": getattr(next_slot, "slot", None)
    }

@app.post("/api/v1/route/autofill", summary="Intelligently Auto-Fill Sequential Route Waypoint Gaps")
async def autofill_route_endpoint(request: Request):
    body = await request.json()
    dep_icao = body.get("departureIcao", "").strip().upper()
    arr_icao = body.get("arrivalIcao", "").strip().upper()
    wps = body.get("waypoints", [])

    dep_airport = aero_store.airports.get(dep_icao)
    if not dep_airport:
        raise HTTPException(status_code=400, detail=f"Departure aerodrome '{dep_icao}' not found.")
    arr_airport = aero_store.airports.get(arr_icao)
    if not arr_airport:
        raise HTTPException(status_code=400, detail=f"Arrival aerodrome '{arr_icao}' not found.")

    res = autofill_route(
        dep_airport=dep_airport,
        arr_airport=arr_airport,
        selected_waypoints=wps,
        all_waypoints=aero_store.waypoints,
        routes=aero_store.routes
    )
    return res

@app.get("/api/v1/waypoints/{name}/alternates", summary="Get Topological Lateral Alternates for Waypoint")
def get_waypoint_alternates_endpoint(name: str, limit: int = 5):
    graph = get_airspace_graph()
    clean = name.strip().upper()
    alts = graph.get_waypoint_alternates(clean, limit=limit)
    return {
        "waypoint": clean,
        "alternates": alts,
        "details": [
            graph.nodes.get(a, {"name": a}) for a in alts
        ]
    }

@app.post("/api/v1/route/shortest-path", summary="Calculate A* Shortest Path through Airspace Graph")
async def calculate_shortest_path_endpoint(request: Request):
    body = await request.json()
    start = body.get("start", "").strip().upper()
    end = body.get("end", "").strip().upper()
    avoid = set(body.get("avoidWaypoints", []))

    if not start or not end:
        raise HTTPException(status_code=400, detail="start and end waypoints are required.")

    graph = get_airspace_graph()
    path, dist = graph.shortest_path(start, end, avoid=avoid)
    if not path:
        raise HTTPException(status_code=404, detail=f"No connected route found between '{start}' and '{end}'.")

    return {
        "start": start,
        "end": end,
        "totalDistanceNm": dist,
        "waypointCount": len(path),
        "waypoints": path,
        "avoidedWaypoints": list(avoid)
    }

@app.post("/api/v1/route/alternatives", summary="Generate K-Shortest Alternative Airspace Corridors")
async def calculate_alternative_paths_endpoint(request: Request):
    body = await request.json()
    start = body.get("start", "").strip().upper()
    end = body.get("end", "").strip().upper()
    k = int(body.get("count", 3))
    avoid = set(body.get("avoidWaypoints", []))

    if not start or not end:
        raise HTTPException(status_code=400, detail="start and end waypoints are required.")

    graph = get_airspace_graph()
    alternatives = graph.find_alternative_paths(start, end, k=k, avoid=avoid)
    return {
        "start": start,
        "end": end,
        "pathCount": len(alternatives),
        "alternatives": alternatives
    }

# -------------------------------------------------------------
# 2. 4D Trajectory Calculation & Deconfliction Preview
# -------------------------------------------------------------
@app.post("/api/v1/trajectory/calculate", summary="Calculate 4D Trajectory & Deconfliction")
async def calculate_trajectory(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    dep_icao = body.get("departureIcao", "").upper()
    arr_icao = body.get("arrivalIcao", "").upper()
    ac_type = body.get("aircraftType", "A320")
    requested_fl = int(body.get("requestedCruiseFl", 280))
    wp_names = body.get("waypointNames", [])
    eobt_str = body.get("estimatedOffBlockTime")
    etot_str = body.get("estimatedTakeOffTime") or body.get("etot")
    dep_runway = body.get("departureRunway")
    arr_runway = body.get("arrivalRunway")

    dep_airport = aero_store.airports.get(dep_icao)
    if not dep_airport:
        raise HTTPException(status_code=400, detail=f"Departure aerodrome '{dep_icao}' not found.")

    arr_airport = aero_store.airports.get(arr_icao)
    if not arr_airport:
        raise HTTPException(status_code=400, detail=f"Arrival aerodrome '{arr_icao}' not found.")

    waypoints = []
    for w in wp_names:
        wp_obj = aero_store.waypoints.get(w.upper())
        if wp_obj:
            waypoints.append(wp_obj)

    etot_dt = datetime.fromisoformat(etot_str.replace("Z", "")) if etot_str else None
    eobt_dt = datetime.fromisoformat(eobt_str.replace("Z", "")) if eobt_str else (
        None if etot_dt else datetime.now(timezone.utc).replace(tzinfo=None)
    )

    cruise_tas_override = body.get("cruiseTasOverride") or body.get("cruiseTas")

    calc_result = calculate_4d_trajectory(
        dep_airport=dep_airport,
        arr_airport=arr_airport,
        waypoints=waypoints,
        aircraft_type=ac_type,
        requested_fl=requested_fl,
        eobt_dt=eobt_dt,
        etot_dt=etot_dt,
        firs=list(aero_store.firs.values()),
        cruise_tas_override=int(cruise_tas_override) if cruise_tas_override else None,
        departure_runway=dep_runway,
        arrival_runway=arr_runway
    )

    # 4D Deconfliction check against active plans in SQLite
    res_eobt_str = calc_result.get("eobt", "").replace("Z", "")
    res_eldt_str = calc_result.get("eldt", "").replace("Z", "")
    candidate_eobt = datetime.fromisoformat(res_eobt_str) if res_eobt_str else (eobt_dt or datetime.now(timezone.utc).replace(tzinfo=None))

    eta_dt = candidate_eobt
    if calc_result["points"]:
        last_pt_time = calc_result["points"][-1]["estimatedTimestamp"].replace("Z", "")
        eta_dt = datetime.fromisoformat(last_pt_time)
    candidate_eta = datetime.fromisoformat(res_eldt_str) if res_eldt_str else eta_dt

    callsign = body.get("callsign", "CANDIDATE")
    temp_gufi = "preview-" + generate_gufi()
    outcome = deconflict_trajectory(
        candidate_gufi=temp_gufi,
        candidate_callsign=callsign,
        candidate_points=calc_result["points"],
        candidate_eobt=candidate_eobt,
        candidate_eta=candidate_eta,
        db=db,
        log_to_db=False, # Only preview, do not record in DB yet
        aircraft_type=ac_type
    )

    calc_result["deconfliction"] = {
        "hasConflicts": outcome.has_conflicts,
        "conflictCount": len(outcome.conflicts),
        "conflicts": [c.to_dict() for c in outcome.conflicts],
        "resolutions": outcome.resolutions,
        "comprehensiveSolutions": outcome.comprehensive_solutions
    }

    return {
        "calculated": calc_result,
        "departureAirport": dep_airport,
        "arrivalAirport": arr_airport
    }

@app.post("/api/v1/trajectory/check-conflicts", summary="Test 4D Airspace Conflicts for Candidate Plan")
async def check_conflicts_endpoint(request: Request, db: Session = Depends(get_db)):
    """
    Dedicated endpoint to test a plan for 4D conflicts against the database without filing it.
    """
    body = await request.json()
    callsign = body.get("callsign", "TEST_FLIGHT")
    pts_4d = body.get("points4D", [])
    if not pts_4d:
        raise HTTPException(status_code=400, detail="points4D array is required to evaluate separation.")

    eobt_str = pts_4d[0]["estimatedTimestamp"].replace("Z", "")
    eta_str = pts_4d[-1]["estimatedTimestamp"].replace("Z", "")
    eobt_dt = datetime.fromisoformat(eobt_str)
    eta_dt = datetime.fromisoformat(eta_str)

    temp_gufi = "test-" + generate_gufi()
    ac_type = body.get("aircraftType", "A320")
    outcome = deconflict_trajectory(
        candidate_gufi=temp_gufi,
        candidate_callsign=callsign,
        candidate_points=pts_4d,
        candidate_eobt=eobt_dt,
        candidate_eta=eta_dt,
        db=db,
        log_to_db=False,
        aircraft_type=ac_type
    )

    return {
        "hasConflicts": outcome.has_conflicts,
        "conflictCount": len(outcome.conflicts),
        "conflicts": [c.to_dict() for c in outcome.conflicts],
        "resolutions": outcome.resolutions,
        "comprehensiveSolutions": outcome.comprehensive_solutions
    }

# -------------------------------------------------------------
# 3. Flight Plan Filing, Retrieval, Modification & Cancellation
# -------------------------------------------------------------
@app.post("/api/v1/ffice/plans", summary="Submit / File an FF-ICE Plan (SWIM POST)")
async def file_plan(
    request: Request,
    strict_deconfliction: bool = Query(False, description="Reject plan if 4D conflict is detected"),
    db: Session = Depends(get_db)
):
    content_type = request.headers.get("content-type", "")
    raw_body = (await request.body()).decode("utf-8")

    if "xml" in content_type or raw_body.strip().startswith("<"):
        plan_dict = parse_fixm_xml(raw_body)
    else:
        plan_dict = json.loads(raw_body)

    # Check for strict_deconfliction flag in body if present
    if plan_dict.get("strictDeconfliction") is not None:
        strict_deconfliction = bool(plan_dict.get("strictDeconfliction"))

    callsign = plan_dict.get("flightIdentification", {}).get("aircraftIdentification", "UNTITLED")
    dep = plan_dict.get("departure", {})
    arr = plan_dict.get("arrival", {})
    ac = plan_dict.get("aircraft", {})
    traj = plan_dict.get("trajectory", {})
    pts_4d = traj.get("points4D", [])

    dep_icao = dep.get("aerodrome", "")
    arr_icao = arr.get("aerodrome", "")

    # Central GUFI Coordination (ICAO Doc 9965 Central Register Placeholder)
    gufi = plan_dict.get("gufi")
    if not gufi or gufi == "00000000-0000-0000-0000-000000000000" or gufi.startswith("preview-"):
        allocated = allocate_central_gufi(
            callsign=callsign,
            departure_icao=dep_icao,
            arrival_icao=arr_icao,
            eobt=dep.get("estimatedOffBlockTime")
        )
        gufi = allocated["gufi"]
        plan_dict["gufi"] = gufi

    clean_gufi = gufi.replace("urn:uuid:", "").strip()

    commit_central_gufi(gufi, {
        "callsign": callsign,
        "departureIcao": dep_icao,
        "arrivalIcao": arr_icao,
        "status": "COMMITTED"
    })

    # Taxi and Runway Operational Modes (ICAO Doc 9643 / EOBT vs ETOT)
    taxi_out_min = int(dep.get("taxiOutMinutes") or get_airport_taxi_out_minutes(dep_icao))
    taxi_in_min = int(arr.get("taxiInMinutes") or get_airport_taxi_in_minutes(arr_icao))

    etot_str = dep.get("estimatedTakeOffTime") or dep.get("etot")
    eobt_str = dep.get("estimatedOffBlockTime") or dep.get("eobt")

    if etot_str and not eobt_str:
        etot_dt = datetime.fromisoformat(etot_str.replace("Z", ""))
        eobt_dt = etot_dt - timedelta(minutes=taxi_out_min)
    elif eobt_str:
        eobt_dt = datetime.fromisoformat(eobt_str.replace("Z", ""))
        etot_dt = datetime.fromisoformat(etot_str.replace("Z", "")) if etot_str else (eobt_dt + timedelta(minutes=taxi_out_min))
    else:
        eobt_dt = datetime.now(timezone.utc).replace(tzinfo=None)
        etot_dt = eobt_dt + timedelta(minutes=taxi_out_min)

    eta_str = arr.get("estimatedTimeOfArrival") or arr.get("eta") or arr.get("eldt")
    if eta_str:
        eldt_dt = datetime.fromisoformat(eta_str.replace("Z", ""))
    elif pts_4d:
        last_t = pts_4d[-1].get("estimatedTimestamp", "").replace("Z", "")
        eldt_dt = datetime.fromisoformat(last_t) if last_t else (etot_dt + timedelta(hours=1))
    else:
        eldt_dt = etot_dt + timedelta(hours=1)
    eibt_dt = eldt_dt + timedelta(minutes=taxi_in_min)

    # Reflect standard timings & runway operational mode in plan_dict
    dep["estimatedOffBlockTime"] = eobt_dt.isoformat() + "Z"
    dep["eobt"] = dep["estimatedOffBlockTime"]
    dep["estimatedTakeOffTime"] = etot_dt.isoformat() + "Z"
    dep["etot"] = dep["estimatedTakeOffTime"]
    dep["taxiOutMinutes"] = taxi_out_min
    dep["operationalMode"] = get_airport_runway_mode(dep_icao)

    arr["estimatedTimeOfArrival"] = eldt_dt.isoformat() + "Z"
    arr["eta"] = arr["estimatedTimeOfArrival"]
    arr["estimatedTouchdownTime"] = eldt_dt.isoformat() + "Z"
    arr["eldt"] = arr["estimatedTouchdownTime"]
    arr["estimatedInBlockTime"] = eibt_dt.isoformat() + "Z"
    arr["eibt"] = arr["estimatedInBlockTime"]
    arr["taxiInMinutes"] = taxi_in_min
    arr["operationalMode"] = get_airport_runway_mode(arr_icao)

    # 4D Strategic Deconfliction check & log
    ac_type = ac.get("aircraftType", "A320")
    outcome = deconflict_trajectory(
        candidate_gufi=gufi,
        candidate_callsign=callsign,
        candidate_points=pts_4d,
        candidate_eobt=eobt_dt,
        candidate_eta=eldt_dt,
        db=db,
        log_to_db=not strict_deconfliction, # Only log if accepted or non-strict
        aircraft_type=ac_type
    )

    # STRICT ENFORCEMENT CHECK
    if strict_deconfliction and outcome.has_conflicts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "status": "REJECTED",
                "error": "Flight plan rejected by SWIM Airspace Manager due to 4D airspace separation conflict.",
                "conflictCount": len(outcome.conflicts),
                "conflicts": [c.to_dict() for c in outcome.conflicts],
                "resolutions": outcome.resolutions,
                "comprehensiveSolutions": outcome.comprehensive_solutions
            }
        )

    plan_dict["status"] = "FILED"
    plan_dict["filingTime"] = datetime.now(timezone.utc).isoformat() + "Z"
    fixm_xml_str = serialize_to_fixm_xml(plan_dict)
    fixm_json_str = json.dumps(plan_dict)

    # Check if plan already exists in DB
    existing = db.query(FlightPlanModel).filter(
        (FlightPlanModel.gufi == clean_gufi) | (FlightPlanModel.gufi == gufi)
    ).first()
    if existing:
        db.delete(existing)
        db.flush()

    # Save Flight Plan to SQLite
    db_plan = FlightPlanModel(
        gufi=clean_gufi,
        callsign=callsign,
        registration=plan_dict.get("flightIdentification", {}).get("aircraftRegistration"),
        status="FILED",
        message_type="FILING",
        departure_icao=dep_icao,
        departure_runway=dep.get("runway"),
        departure_elevation_ft=dep.get("elevationFeet", 0),
        eobt=eobt_dt,
        etot=etot_dt,
        taxi_out_minutes=taxi_out_min,
        arrival_icao=arr_icao,
        arrival_runway=arr.get("runway"),
        arrival_elevation_ft=arr.get("elevationFeet", 0),
        eta=eldt_dt,
        eldt=eldt_dt,
        taxi_in_minutes=taxi_in_min,
        aircraft_type=ac.get("aircraftType", "A320"),
        wake_turbulence=ac.get("wakeTurbulence", "M"),
        equipment=ac.get("capabilities", {}).get("standardEquipment", "SDFGIRW/LB1"),
        cruising_level=plan_dict.get("enRoute", {}).get("cruisingLevel", "F280"),
        cruising_speed=plan_dict.get("enRoute", {}).get("cruisingSpeed", "N0450"),
        route_string=plan_dict.get("enRoute", {}).get("routeString", ""),
        total_distance_nm=traj.get("totalDistanceNm", 0.0),
        total_flight_time_minutes=traj.get("totalFlightTimeMinutes", 0.0),
        fixm_json=fixm_json_str,
        fixm_xml=fixm_xml_str,
        remarks=plan_dict.get("remarks")
    )
    db.add(db_plan)
    db.flush()

    # Save 4D Trajectory Points to SQLite for spatial querying
    for idx, pt in enumerate(pts_4d):
        c = pt.get("coordinates", {})
        t_str = pt.get("estimatedTimestamp", "").replace("Z", "")
        pt_dt = datetime.fromisoformat(t_str) if t_str else eobt_dt
        db_pt = TrajectoryPointModel(
            gufi=clean_gufi,
            point_index=idx,
            point_type=pt.get("pointType", "WAYPOINT"),
            identifier=pt.get("identifier", "WPT"),
            latitude=c.get("latitude", 0.0),
            longitude=c.get("longitude", 0.0),
            altitude_feet=pt.get("altitudeFeet", 0),
            flight_level=pt.get("flightLevel", 0),
            cumulative_distance_nm=pt.get("cumulativeDistanceNm", 0.0),
            ground_speed_knots=pt.get("groundSpeedKnots", 450),
            timestamp=pt_dt,
            airspace=pt.get("associatedAirspace")
        )
        db.add(db_pt)

    db.commit()

    # Content negotiation
    accept = request.headers.get("accept", "")
    if "xml" in accept or "vnd.fixm+xml" in accept:
        return Response(content=fixm_xml_str, media_type="application/vnd.fixm+xml")

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "plan": plan_dict,
            "deconfliction": {
                "hasConflicts": outcome.has_conflicts,
                "conflictCount": len(outcome.conflicts),
                "conflicts": [c.to_dict() for c in outcome.conflicts],
                "resolutions": outcome.resolutions,
                "comprehensiveSolutions": outcome.comprehensive_solutions
            }
        }
    )

@app.get("/api/v1/ffice/plans", summary="List Filed Flight Plans from Database")
def list_plans(
    callsign: Optional[str] = None,
    departure: Optional[str] = None,
    arrival: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    active_only: bool = Query(True, description="Only list upcoming and active in-flight plans (default True)"),
    include_expired: bool = Query(False, description="Include completed or expired historical plans"),
    db: Session = Depends(get_db)
):
    """
    List filed flight plans with automatic lifecycle pruning.
    By default (active_only=True), only returns flight plans that are upcoming
    (now < EOBT) or likely still in flight (EOBT <= now <= ETA + 45min).
    Old completed flights (> ETA + 45min) and no-shows (> EOBT + 120min) are pruned.
    """
    # Run immediate lifecycle sweep to ensure fresh state
    sweep_expired_flight_plans(db)

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now_utc - timedelta(minutes=ETA_BUFFER_MINUTES)

    query = db.query(FlightPlanModel)
    if callsign:
        query = query.filter(FlightPlanModel.callsign.ilike(f"%{callsign}%"))
    if departure:
        query = query.filter(FlightPlanModel.departure_icao == departure.upper())
    if arrival:
        query = query.filter(FlightPlanModel.arrival_icao == arrival.upper())

    if status_filter:
        query = query.filter(FlightPlanModel.status == status_filter.upper())
    elif active_only and not include_expired:
        # User requested: only upcoming or likely still in flight
        query = query.filter(
            FlightPlanModel.status.in_(["FILED", "AGREED", "ACTIVE"]),
            FlightPlanModel.eta >= cutoff
        )

    results = []
    for p in query.order_by(FlightPlanModel.created_at.desc()).all():
        try:
            d = json.loads(p.fixm_json)
            # Decorate with real-time operational status
            op_phase = determine_operational_status(p, now_utc)
            d["operationalStatus"] = op_phase
            d["isLikelyInFlight"] = (op_phase == "IN_FLIGHT")
            d["isUpcoming"] = (op_phase == "UPCOMING")
            results.append(d)
        except Exception:
            pass
    return results

@app.post("/api/v1/ffice/plans/sweep", summary="Trigger Background Plan Lifecycle Sweep")
def sweep_plans_endpoint(db: Session = Depends(get_db)):
    """
    Manually triggers the background sweeper to transition stale or completed
    flight plans to COMPLETED or EXPIRED.
    """
    result = sweep_expired_flight_plans(db)
    return {
        "status": "SUCCESS",
        "message": f"Swept {result['totalSwept']} flight plans ({result['completed']} completed, {result['expired']} expired).",
        "swept": result,
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
    }


@app.get("/api/v1/ffice/plans/{gufi}", summary="Retrieve Flight Plan by GUFI")
def get_plan(gufi: str, request: Request, db: Session = Depends(get_db)):
    clean_gufi = gufi.replace("urn:uuid:", "").strip()
    plan = db.query(FlightPlanModel).filter(
        (FlightPlanModel.gufi == clean_gufi) | (FlightPlanModel.gufi == gufi)
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail=f"Flight plan with GUFI '{gufi}' not found.")

    accept = request.headers.get("accept", "")
    if "xml" in accept or "vnd.fixm+xml" in accept:
        return Response(content=plan.fixm_xml, media_type="application/vnd.fixm+xml")
    return Response(content=plan.fixm_json, media_type="application/json")

@app.delete("/api/v1/ffice/plans/{gufi}", summary="Cancel Flight Plan")
def cancel_plan(gufi: str, db: Session = Depends(get_db)):
    clean_gufi = gufi.replace("urn:uuid:", "").strip()
    plan = db.query(FlightPlanModel).filter(
        (FlightPlanModel.gufi == clean_gufi) | (FlightPlanModel.gufi == gufi)
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail=f"Flight plan with GUFI '{gufi}' not found.")

    plan.status = "CANCELLED"
    plan.message_type = "CANCELLATION"
    data = json.loads(plan.fixm_json)
    data["status"] = "CANCELLED"
    data["messageType"] = "CANCELLATION"
    plan.fixm_json = json.dumps(data)
    plan.fixm_xml = serialize_to_fixm_xml(data)
    db.commit()

    # Release centrally coordinated GUFI
    release_central_gufi(clean_gufi, "CANCELLED")

    return {"gufi": gufi, "status": "CANCELLED"}

@app.get("/api/v1/conflicts", summary="View Active 4D Airspace Conflicts")
def list_conflicts(db: Session = Depends(get_db)):
    records = db.query(ConflictRecordModel).order_by(ConflictRecordModel.detected_at.desc()).limit(50).all()
    return [
        {
            "id": r.id,
            "gufi1": r.gufi1,
            "callsign1": r.callsign1,
            "gufi2": r.gufi2,
            "callsign2": r.callsign2,
            "type": r.conflict_type,
            "minHorizontalNm": r.min_horizontal_separation_nm,
            "minVerticalFt": r.min_vertical_separation_ft,
            "timeOfClosestApproach": r.time_of_closest_approach.isoformat() + "Z",
            "latitude": r.latitude,
            "longitude": r.longitude,
            "severity": r.severity,
            "resolution": r.resolution_advisory,
            "detectedAt": r.detected_at.isoformat() + "Z"
        }
        for r in records
    ]

@app.post("/api/v1/traffic/generate", summary="Generate Realistic Flight Traffic (Populate DB)")
def generate_traffic_endpoint(
    count: int = Query(20, ge=1, le=100, description="Number of realistic flight plans to generate"),
    hours: float = Query(6.0, ge=0.5, le=48.0, description="Time window in hours from now"),
    db: Session = Depends(get_db)
):
    """
    Generates realistic commercial airline flights connecting major UK & Irish airports
    and populates SQLite database. Evaluates 4D deconfliction.
    """
    plans = generate_realistic_traffic(count=count, hours=hours, db=db, store=aero_store)
    return {
        "status": "SUCCESS",
        "generatedCount": len(plans),
        "message": f"Successfully generated {len(plans)} realistic flights across the next {hours:.1f} hours and saved to SQLite DB."
    }

# -------------------------------------------------------------
# 4. Static UI Hosting
# -------------------------------------------------------------
client_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "client"))
if os.path.isdir(client_dir):
    app.mount("/", StaticFiles(directory=client_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "3000"))
    print("\n" + "="*56)
    print("✈️  PYTHON SWIM FF-ICE FLIGHT PLANNING & DECONFLICTION SERVER")
    print(f"📡 Server Address: http://localhost:{port}")
    print(f"📖 OpenAPI Docs:   http://localhost:{port}/docs")
    print(f"🗄️  SQLite DB:      {os.path.abspath(DB_PATH)}")
    print("="*56 + "\n")
    uvicorn.run("ff_ice_server.main:app", host="0.0.0.0", port=port, reload=False)
