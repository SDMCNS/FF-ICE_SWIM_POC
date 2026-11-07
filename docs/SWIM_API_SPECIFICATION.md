# SWIM FF-ICE REST API Specification
## ICAO Doc 10039 Yellow Profile Compliant Service Layer

---

## 1. Overview & Base URL

The SWIM (System-Wide Information Management) REST interface exposes high-fidelity flight planning, 4D trajectory advisory, strategic airspace deconfliction, and aeronautical reference data services.

* **Base URL:** `http://127.0.0.1:3000`
* **Interactive OpenAPI Docs:** `http://127.0.0.1:3000/docs`
* **OpenAPI 3.0 Spec:** `http://127.0.0.1:3000/openapi.json`
* **Content Negotiation:** Supports `application/json` and `application/vnd.fixm+xml`.

---

## 2. API Endpoints Summary

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/trajectory/calculate` | Calculates 4D trajectory, TOC/TOD, FIR crossings, and previews deconfliction. |
| `POST` | `/api/v1/trajectory/check-conflicts` | Dedicated separation check for candidate trajectory points. |
| `POST` | `/api/v1/ffice/plans` | Files a new FF-ICE plan with SQLite persistence, GUFI assignment, and strict deconfliction. |
| `GET` | `/api/v1/ffice/plans` | Queries filed plans with filters (callsign, aerodromes, status). |
| `GET` | `/api/v1/ffice/plans/{gufi}` | Retrieves filed plan by GUFI (supports FIXM XML or JSON negotiation). |
| `DELETE` | `/api/v1/ffice/plans/{gufi}` | Cancels a filed flight plan. |
| `GET` | `/api/v1/conflicts` | Lists active 4D loss-of-separation records logged in the database. |
| `GET` | `/api/v1/weather/metar` | Queries live NOAA METAR, TAF, and dynamic active runway headwind/crosswind. |
| `POST` | `/api/v1/route/autofill` | Intelligently auto-fills route waypoint gaps and connects ATS airways. |
| `POST` | `/api/v1/route/shortest-path` | Calculates $A^*$ shortest path through the 1,061-node aeronautical graph. |
| `POST` | `/api/v1/route/alternatives` | Generates $K$-shortest alternative corridors with distance deltas. |
| `GET` | `/api/v1/waypoints/{name}/alternates` | Returns topological graph detour alternates for any waypoint. |
| `POST` | `/api/v1/traffic/generate` | Populates database with $X$ realistic commercial flights over $Y$ hours. |
| `POST` | `/api/v1/aero/rebuild` | Dynamically rebuilds all aeronautical datasets, airspace graph, and runway configurations from disk. |
| `GET` | `/api/v1/airports/{icao}/runways` | Retrieves physical concrete strips, canonical reciprocal pairs, and segregated operational roles. |
| `GET` | `/api/v1/airports` | Searches aerodromes across all ingested datasets by ICAO or name. |
| `GET` | `/api/v1/waypoints` | Searches aeronautical waypoints across all ingested datasets by code. |
| `GET` | `/api/v1/airspace/fir` | Returns UK & Irish 3D FIR polyhedra. |
| `GET` | `/api/v1/aircraft` | Returns performance envelope parameters for supported aircraft types. |
| `POST` | `/api/v1/registry/gufi/allocate` | Centrally allocates an authoritative GUFI (ICAO Doc 9965 placeholder). |
| `GET` | `/api/v1/registry/gufi/{gufi}/verify` | Verifies GUFI registration with Central Registry authority. |
| `GET` | `/api/v1/registry/gufi` | Lists all centrally coordinated GUFIs and commitment statuses. |
| `GET` | `/api/v1/swim/service-description` | Returns official Service Description Document (SDD) for Yellow Profile. |
| `GET` | `/api/v1/swim/health` | Standard Yellow Profile liveness and database health status. |
| `GET` | `/api/v1/swim/status` | Operational throughput, active plans, and supported runway operational modes. |

---

## 3. Detailed Endpoint Documentation

### 3.1 Calculate 4D Trajectory
**`POST /api/v1/trajectory/calculate`**

Calculates the complete 4D profile including:
- $5.0\text{ NM}$ straight departure climb (`RWY{rwy}_5NM`)
- Dynamic Top of Climb (TOC) and Top of Descent (TOD)
- 3D FIR boundary crossings (`EGTT`, `EGPX`, `EISN`)
- $17.0\text{ NM}$ stabilized $3^\circ$ ILS localizer intercept (`ILS{rwy}_17NM`)
- 4D Strategic deconfliction preview with comprehensive solution recommendations

#### Request Payload
```json
{
  "departureIcao": "EGLL",
  "arrivalIcao": "EIDW",
  "aircraftType": "A320",
  "requestedCruiseFl": 280,
  "waypointNames": ["LUXTO", "PEPZE", "SUROX", "LIPGO"],
  "estimatedOffBlockTime": "2026-11-07T16:00:00Z",
  "departureRunway": "27R",
  "arrivalRunway": "28L",
  "callsign": "EIN157"
}
```

#### Response (200 OK)
```json
{
  "calculated": {
    "totalDistanceNm": 248.3,
    "totalFlightTimeMinutes": 41.5,
    "points": [
      {
        "pointType": "DEPARTURE",
        "identifier": "EGLL",
        "coordinates": {"latitude": 51.4775, "longitude": -0.4614},
        "altitudeFeet": 83,
        "flightLevel": 1,
        "cumulativeDistanceNm": 0.0,
        "groundSpeedKnots": 320,
        "estimatedTimestamp": "2026-11-07T16:00:00Z"
      },
      {
        "pointType": "INITIAL_CLIMB",
        "identifier": "RWY27R_5NM",
        "coordinates": {"latitude": 51.4772, "longitude": -0.5947},
        "altitudeFeet": 1500,
        "flightLevel": 15,
        "cumulativeDistanceNm": 5.0,
        "groundSpeedKnots": 340,
        "estimatedTimestamp": "2026-11-07T16:00:56Z"
      },
      {
        "pointType": "TOC",
        "identifier": "TOC",
        "coordinates": {"latitude": 52.0123, "longitude": -2.3412},
        "altitudeFeet": 28000,
        "flightLevel": 280,
        "cumulativeDistanceNm": 68.2,
        "groundSpeedKnots": 450,
        "estimatedTimestamp": "2026-11-07T16:11:02Z"
      },
      {
        "pointType": "APPROACH_INTERCEPT",
        "identifier": "ILS28L_17NM",
        "coordinates": {"latitude": 53.4214, "longitude": -5.7982},
        "altitudeFeet": 5406,
        "flightLevel": 54,
        "cumulativeDistanceNm": 231.3,
        "groundSpeedKnots": 290,
        "estimatedTimestamp": "2026-11-07T16:38:15Z"
      },
      {
        "pointType": "DESTINATION",
        "identifier": "EIDW",
        "coordinates": {"latitude": 53.4214, "longitude": -6.2700},
        "altitudeFeet": 243,
        "flightLevel": 2,
        "cumulativeDistanceNm": 248.3,
        "groundSpeedKnots": 290,
        "estimatedTimestamp": "2026-11-07T16:41:30Z"
      }
    ],
    "deconfliction": {
      "hasConflicts": false,
      "conflictCount": 0,
      "conflicts": [],
      "comprehensiveSolutions": []
    }
  }
}
```

---

### 3.2 File FF-ICE Flight Plan
**`POST /api/v1/ffice/plans`**

Files a plan into the SQLite database. Enforces strict deconfliction if requested.

#### Headers
- `Content-Type: application/json` or `application/vnd.fixm+xml`
- `Accept: application/json` or `application/vnd.fixm+xml`

#### Query Parameters
- `strict_deconfliction` (bool, default `false`): If `true`, returns `409 Conflict` and rejects the plan if any separation minimum is violated.

#### Success Response (201 Created)
Returns JSON or FIXM XML based on content negotiation with assigned immutable GUFI (`urn:uuid:b8503211-9abe-4ae6-b437-86fab45f2ff8`).

---

### 3.3 Topological Graph Shortest Path Routing
**`POST /api/v1/route/shortest-path`**

Calculates the $A^*$ shortest airway path across the 1,061-node navigation graph.

#### Request Payload
```json
{
  "start": "LUXTO",
  "end": "LIPGO",
  "avoidWaypoints": ["BERUL", "SEMMU"]
}
```

#### Response (200 OK)
```json
{
  "start": "LUXTO",
  "end": "LIPGO",
  "totalDistanceNm": 161.4,
  "waypointCount": 9,
  "waypoints": ["LUXTO", "FITBO", "EDFAR", "LUCSA", "PEPZE", "SEMMU", "BADSI", "MORAG", "LIPGO"],
  "avoidedWaypoints": ["BERUL"]
}
```

---

### 3.4 Live NOAA METAR & Active Runway Determination
**`GET /api/v1/weather/metar?icao=EGLL`**

Fetches live observation from NOAA Aviation Weather Center and computes headwind/crosswind vectors across all runways.

#### Response (200 OK)
```json
{
  "icao": "EGLL",
  "name": "London Heathrow",
  "country": "GB",
  "elevation": 83,
  "metar": {
    "rawOb": "EGLL 071220Z 24014KT 9999 FEW025 12/06 Q1018",
    "windDirection": 240,
    "windSpeedKnots": 14,
    "flightCategory": "VFR"
  },
  "activeRunway": {
    "activeRunway": "27R",
    "runwayHeading": 269.7,
    "headwindKnots": 12.2,
    "crosswindKnots": 6.8,
    "explanation": "Active runway 27R selected into wind (240° at 14 kt): Headwind 12.2 kts, Crosswind 6.8 kts.",
    "allRunways": [
      {
        "designator": "27R",
        "heading": 269.7,
        "headwind": 12.2,
        "crosswind": 6.8,
        "isActive": true
      },
      {
        "designator": "09L",
        "heading": 89.7,
        "headwind": -12.2,
        "crosswind": -6.8,
        "isActive": false
      }
    ]
  }
}
```

---

### 3.5 Rebuild Aeronautical Datasets & Navigation Mesh
**`POST /api/v1/aero/rebuild`**

Hot-reloads aerodrome data, waypoints, ATS routes, and FIR geometries from their respective directories across any region. Reconstructs the topological navigation mesh ($A^*$ shortest path and alternatives) and synthesizes operational runway modes dynamically without requiring a server restart.

#### Response (200 OK)
```json
{
  "status": "SUCCESS",
  "message": "Aeronautical database, airspace graph, and airport runway operations successfully rebuilt.",
  "airportsCount": 119,
  "waypointsCount": 1057,
  "routesCount": 9,
  "firsCount": 8,
  "graphNodesCount": 1057,
  "operationalAirportsCount": 14,
  "timestamp": "2026-11-07T16:05:00.000000Z"
}
```

---

### 3.6 Aerodrome Physical Concrete Strips & Runway Operations
**`GET /api/v1/airports/{icao}/runways`**

Retrieves the physical concrete strips, canonical reciprocal runway pairs, and designated arrival/departure roles for an aerodrome. Conforms to ICAO Doc 9643 (SOIR) segregated parallel operations.

#### Response (200 OK - EGLL)
```json
{
  "icao": "EGLL",
  "mode": "PARALLEL_SEGREGATED",
  "physicalStrips": [
    {
      "stripId": "09L/27R",
      "runwayEnds": ["09L", "27R"],
      "lengthMeters": 3902,
      "widthMeters": 50,
      "surface": "ASPHALT",
      "complex": "NORTH_COMPLEX",
      "segregatedRole": {
        "WEST": "ARRIVAL",
        "EAST": "ARRIVAL"
      },
      "description": "Northern physical concrete strip (09L/27R). Exclusively handles arrivals."
    },
    {
      "stripId": "09R/27L",
      "runwayEnds": ["09R", "27L"],
      "lengthMeters": 3660,
      "widthMeters": 50,
      "surface": "ASPHALT",
      "complex": "SOUTH_COMPLEX",
      "segregatedRole": {
        "WEST": "DEPARTURE",
        "EAST": "DEPARTURE"
      },
      "description": "Southern physical concrete strip (09R/27L). Exclusively handles departures."
    }
  ],
  "westOperations": {
    "departureRunways": ["27L"],
    "arrivalRunways": ["27R"]
  },
  "eastOperations": {
    "departureRunways": ["09R"],
    "arrivalRunways": ["09L"]
  },
  "taxiOutMinutes": 15,
  "taxiInMinutes": 8
}
```

---

### 3.7 Central GUFI Registry Allocation
**`POST /api/v1/registry/gufi/allocate`**

Allocates an authoritative, globally unique flight identifier according to ICAO Doc 9965 Central Register principles.

#### Request Payload
```json
{
  "callsign": "EIN157",
  "departureIcao": "EGLL",
  "arrivalIcao": "EIDW",
  "eobt": "2026-11-07T16:00:00Z"
}
```

#### Response (201 Created)
```json
{
  "status": "ALLOCATED",
  "gufi": "b8503211-9abe-4ae6-b437-86fab45f2ff8",
  "urn": "urn:uuid:b8503211-9abe-4ae6-b437-86fab45f2ff8",
  "issuingAuthority": "ICAO-CENTRAL-REGISTRY-DEMO",
  "allocatedAt": "2026-11-07T14:00:00.000000Z",
  "flightPlanBinding": {
    "callsign": "EIN157",
    "departureIcao": "EGLL",
    "arrivalIcao": "EIDW",
    "eobt": "2026-11-07T16:00:00Z"
  }
}
```
