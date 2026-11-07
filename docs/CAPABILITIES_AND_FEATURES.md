# FF-ICE & SWIM Proof of Concept (PoC) Capabilities & Operational Feature Matrix
## Next-Generation System-Wide Information Management (SWIM) Flight Planning & 4D Airspace Deconfliction

> **Repository:** [SDMCNS/FF-ICE_SWIM_POC](https://github.com/SDMCNS/FF-ICE_SWIM_POC)  
> **Classification:** Open-Source Proof of Concept (PoC) & Research Reference Implementation  
> **Standard Compliance:** ICAO Doc 9965 (FF-ICE/R), ICAO Doc 10039 (SWIM Yellow Profile), ICAO Doc 9643 (SOIR), ICAO Doc 4444 (PANS-ATM), FIXM Core v4.2+ / iFIXM.  
> **Airspace Coverage:** Location-Agnostic Engine (demonstrated on UK & Irish Airspace: London EGTT, Scottish EGPX, Shannon EISN, Shanwick EGGX, plus international parallel hub models).  

---

> [!IMPORTANT]
> **Proof of Concept (PoC) Notice:**  
> This software is an open-source **Proof of Concept (PoC)** demonstrating the architectural feasibility, 4D trajectory algorithms, and web service protocols defined in ICAO Doc 9965 and EUROCONTROL SWIM standards.

---

## 1. Overview & Operational Paradigm

The **FF-ICE Proof of Concept (PoC)** demonstrates an open-source flight planning, 4D trajectory prediction, and strategic deconfliction service. Engineered to explore the international concepts of **ICAO Doc 9965 (Flight and Flow Information for a Collaborative Environment)**, the PoC models the transition from legacy ATS text-based messaging (ICAO Doc 4444 Model FPL) to digital 4D trajectory negotiation, rich FIXM XML/JSON payloads, and System-Wide Information Management (SWIM) web services.

The PoC provides researchers, aviation software developers, and dispatchers with an interactive, unified operational picture demonstrating conflict-free flight plans across multi-traffic airspace.

---

## 2. Core Capabilities & Feature Breakdown

```
                                      FF-ICE PLATFORM CORE
                                                │
         ┌──────────────────┬───────────────────┼───────────────────┬──────────────────┐
         ▼                  ▼                   ▼                   ▼                  ▼
   4D Trajectory      Global 4D           Aerodrome Runway       NOAA Weather        Topological
   Profile Engine   Deconfliction         Slot & SOIR Engine   & Active Runways    A* Graph Engine
  (5NM / 17NM ILS)  (Zero Collisions)    (Parallel Segregated)  (Live Vectors)    (1061 Fixes / ATS)
```

### 2.1 4D Trajectory Engine with Real-World Terminal Procedures
Unlike rudimentary great-circle distance calculators, the platform generates true, physically grounded 4D trajectories:
* **Standard Terminal Departure (SID) 5 NM Climbout:** Pins aircraft to runway true heading for $5.0\text{ NM}$ post takeoff (`RWY{rwy}_5NM`) up to $1,500\text{ ft AGL}$ with strictly **no turns** permitted below noise abatement altitudes.
* **Standard Terminal Arrival (STAR) 17 NM ILS Intercept:** Computes a stabilized $3^\circ$ ILS glideslope intercept point exactly $17.0\text{ NM}$ out (`ILS{rwy}_17NM`) at $5,400\text{ ft AGL}$ on the runway centerline before final descent.
* **Aerodynamic Performance Profiles:** Integrates climb rates, cruise TAS, descent profiles, and service ceilings for 15+ aircraft types (A320, B738, A321, B77W, A359, B789, E190, AT76, DH8D, C172, etc.).
* **Dynamic TOC / TOD Calculations:** Precise mathematical determination of Top of Climb (TOC) and Top of Descent (TOD) positions, flight levels, and timestamps.
* **3D FIR Boundary Penetrations:** Detects exact spatial coordinates, altitude, and crossing times as trajectories transition across FIR boundaries:
  * `EGTTFIR` / `EGTTUIR` (London FIR / Upper Information Region)
  * `EGPXFIR` / `EGPXUIR` (Scottish FIR / UIR)
  * `EISNFIR` / `EISNUIR` (Shannon FIR / UIR)
  * `EGGXFIR` (Shanwick Oceanic)

---

### 2.2 Global 4D Multi-Traffic Strategic Deconfliction
The platform features an advanced 4D deconfliction solver that evaluates simultaneous traffic interactions:
* **Synchronous Spatial-Temporal Evaluation:** Replaces arbitrary time windows with continuous temporal interpolation $\mathbf{x}_{\text{traffic}}(t)$, checking separation at every second of the flight envelope.
* **Vertical Separation Exemption ($\ge 1,000\text{ ft}$):** Under ICAO RVSM, aircraft are permitted to occupy identical horizontal coordinates provided vertical separation meets or exceeds $1,000\text{ ft}$.
* **Phase-Dependent Horizontal Separation Minima:**
  * **En-Route Airspace:** Enforces $5.0\text{ NM}$ minimum separation when $\Delta z < 1,000\text{ ft}$.
  * **Approach & ILS Intercept Phase ($< 4,000\text{ ft}$):** Enforces $3.0\text{ NM}$ standard separation, dynamically increased up to $6.0\text{ NM}$ based on leading aircraft wake turbulence.
* **Single-Click Comprehensive Deconfliction Solutions:**
  * Rather than generating disconnected, isolated fixes per conflict, the engine computes **system-wide global solutions** that resolve all conflicts simultaneously while preserving flight efficiency (optimal semicircular step-climbs, calibrated slot delays, or speed adjustments).
* **Strict SWIM Enforcement Mode:** When enabled, the service rejects non-compliant flight plans with `409 Conflict`, returning RFC 7807 problem details with exact loss-of-separation diagnostics.

---

### 2.3 Aerodrome Runway Capacity, Physical Concrete Strips & Multi-Parallel Operations (ICAO Doc 9643 SOIR)
The platform distinguishes aerodrome runway topologies to maximize slot capacity without compromising safety:
* **Physical Concrete Strip Isolation:**
  * In real-world parallel operations under ICAO Doc 9643 (SOIR), arriving and departing aircraft **do not share the same strip of concrete**. One runway strip handles departures and another handles arrivals (segregated parallel operations).
  * Slots and ground bookings are keyed to the physical concrete strip (canonical reciprocal pair, e.g. `09L/27R` for arrivals vs `09R/27L` for departures at London Heathrow `EGLL`). An arrival on the northern strip cannot conflict with a departure on the southern strip.
* **Parallel Segregated Operations (`PARALLEL_SEGREGATED`):**
  * At dual parallel airports (London Heathrow `EGLL`, Dublin `EIDW`, Manchester `EGCC`), independent parallel operations unlock full departure and arrival throughput. Departures only maintain wake spacing behind preceding departures on the same departure strip.
* **Multiple Parallel Complexes (`MULTIPLE_PARALLEL`):**
  * Models large aerodromes with multiple sets of parallel runways (e.g. Quad parallel at Paris Charles de Gaulle `LFPG`, multi-parallel complexes at Chicago O'Hare `KORD`, Atlanta `KATL`, and Amsterdam Schiphol `EHAM`).
  * Organizes runways into airfield complexes (e.g. North Doublet and South Doublet at LFPG). Each doublet designates outboard strips for arrivals and inboard strips for departures, preventing taxiway crossings and providing simultaneous independent departure and arrival capacity across four physical strips of concrete.
* **Single Runway Mixed-Mode Interleaving (`MIXED_MODE_SINGLE`):**
  * At single-runway aerodromes (London Gatwick `EGKK 08R/26L`, Stansted `EGSS`, Shannon `EINN`), all arrivals and departures share one physical strip. The engine enforces runway occupancy rollout buffers (75–90s) plus wake vortex decay separation (up to 180s behind Heavy/Super aircraft).
* **Location-Agnostic Ingestion & Dynamic Rebuilding:**
  * Aerodromes, waypoints, ATS routes, and FIR boundaries can be updated or replaced dynamically across any global region.
  * The platform provides `POST /api/v1/aero/rebuild` to hot-reload all aeronautical datasets and reconstruct the topological airspace graph without restarting the server.
  * Newly discovered aerodromes automatically have their operational modes and physical concrete strips synthesized from their AIP runway geometry.
* **5-Minute Airport Slot Allocation Board:** Real-time visual and programmatic scheduling of airport capacity, preventing ground congestion.

---

### 2.4 Precise Trajectory Timing Reconciliation: EOBT vs ETOT
The platform resolves the historical ambiguity between gate pushback and runway wheels-off time:
* **ETOT as Primary Operational Target:** Dispatchers can target an exact runway departure slot (`ETOT`). The system automatically derives off-stand pushback time (`EOBT = ETOT - EXOT`) using aerodrome-specific taxi times (e.g., 20 min for EGLL, 15 min for EIDW, 12 min for EGKK).
* **Arrival In-Block Calculation:** Touchdown occurs at `ELDT` (Estimated Landing Time), and gate arrival occurs at `EIBT = ELDT + EXIT`.
* **Airborne Alignment:** Airborne 4D trajectory timestamps initiate strictly at runway wheels-off (`ETOT`).

---

### 2.5 Real-Time NOAA Weather & Dynamic Active Runway Resolver
Direct live integration with the **NOAA Aviation Weather Center (AWC)**:
* Queries live METAR observations and TAF forecasts for any ICAO aerodrome (`EGLL`, `EIDW`, `EGKK`, `EINN`, etc.).
* Resolves true headwind, tailwind, and crosswind vector components for every runway direction.
* Automatically designates the active operational runway into prevailing winds, applying airport calm-wind preferential runway rules.

---

### 2.6 Topological Airspace Graph Routing & Intelligent Auto-Fill
Built upon a graph network of **1,061 navigational fixes and 5,054 airway edges**:
* **$A^*$ Optimal Shortest Path:** Calculates minimum-distance, airway-compliant flight corridors.
* **$K$-Shortest Alternative Corridors:** Generates detour options with exact distance deltas for contingency planning.
* **Airway Gap Auto-Fill:** Dispatchers select high-level waypoints; the engine automatically fills intermediate navigation fixes and validates ATS airway connectivity (e.g. L18, L149, L975).
* **Interactive Drag-and-Drop Sequencing:** Visual map builder allows clicking, reordering, and deleting route waypoints directly on the aeronautical chart.

---

### 2.7 Authoritative FIXM v4.2+ / iFIXM Engine
Full dual-representation serialization and validation:
* **Core FIXM XML:** Formatted to official schema standards (`xmlns:fx="http://www.fixm.aero/flight/4.2"`, `xmlns:fb="http://www.fixm.aero/base/4.2"`).
* **FIXM JSON:** High-performance, JSON-schema-compliant interchange format.
* **Comprehensive Metadata:** Encodes 4D trajectory points, aircraft capabilities (RNAV 1, B-RNAV, RNP 4, 8.33 kHz, CPDLC, ADS-B), wake categories (`LIGHT`, `MEDIUM`, `HEAVY`, `SUPER`), EOBT, ETOT, ELDT, EIBT, and FIR crossings.

---

### 2.8 SWIM Yellow Profile Service Delivery & Central GUFI Registry
Full compliance with **EUROCONTROL TI-Profile Yellow v2.0** and **ICAO Doc 10039**:
* **Service Description Document (SDD):** Canonical service contract at `/api/v1/swim/service-description` declaring URN `urn:swim:service:ffice:flight-planning:v1`, Request-Response MEPs, QoS, and SLAs.
* **Central GUFI Registry Demonstration Service:** Prevents flight plan collisions across multi-client airline dispatchers by centrally allocating and tracking unique Globally Unique Flight Identifiers (`urn:uuid:...`).
* **RFC 7807 Problem Details:** Unified, structured error responses for all HTTP exceptions.
* **Service Health & Status Monitoring:** Automated operational metrics at `/api/v1/swim/health` and `/api/v1/swim/status`.

---

## 3. Operational Comparison: Legacy FPL vs FF-ICE Platform

| Operational Dimension | Legacy ICAO FPL (Doc 4444) | FF-ICE Platform (Doc 9965 & SWIM) |
| :--- | :--- | :--- |
| **Data Format** | Teletype string (AFTN / Type B) | FIXM v4.2+ XML & RESTful JSON |
| **Trajectory Model** | 2D Waypoint string + Cruise FL | Full 4D Trajectory (Latitude, Longitude, Altitude, Timestamp) |
| **Terminal Departures** | Generic departure aerodrome | $5.0\text{ NM}$ straight climb on active runway heading |
| **Terminal Arrivals** | Generic destination aerodrome | $17.0\text{ NM}$ stabilized $3^\circ$ ILS localizer intercept |
| **Deconfliction** | Tactical radar intervention by ATC | Pre-departure 4D strategic multi-traffic optimization |
| **Runway Operations** | Uncoordinated gate pushback | Wake-separated 5-min runway slots & SOIR parallel capacity |
| **Timing Distinction** | Conflated EOBT | Formal EOBT (stand), ETOT (wheels-off), ELDT, and EIBT |
| **Weather Awareness** | Manual dispatcher review | Automated NOAA live METAR/TAF & active runway resolver |
| **Flight Identifier** | Call sign + Date (non-unique) | Globally Unique Flight Identifier (GUFI UUID v4) |

---

## 4. Documentation Navigation

* **Operational Users & Dispatchers:** Consult the [User Guide](USER_GUIDE.md) for UI workflows.
* **System Integrators & Developers:** Review the [SWIM API Specification](SWIM_API_SPECIFICATION.md).
* **Aviation Regulators & Researchers:** Read the [SWIM Yellow Profile Compliance Audit](SWIM_YELLOW_PROFILE_AUDIT.md).
* **Source Code Repository:** Access the open-source codebase on GitHub at [SDMCNS/FF-ICE_SWIM_POC](https://github.com/SDMCNS/FF-ICE_SWIM_POC).

