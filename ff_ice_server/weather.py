"""
NOAA Aviation Weather Integration for Active Runway Determination.
Queries NOAA Aviation Weather Center (AWC) METAR and TAF APIs for UK and Irish Aerodromes.
Calculates headwind and crosswind components for each runway and resolves the active runway.
"""
import re
import math
import time
import urllib.request
import json
from typing import Optional, Dict, Any, List, Tuple

# In-memory cache: { icao: { "timestamp": float, "data": dict } }
_METAR_CACHE: Dict[str, Dict[str, Any]] = {}
_TAF_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SEC = 300 # 5 minutes

# Calm-wind / preferential active runways for major UK & Irish aerodromes
CALM_WIND_DEFAULTS = {
    "EGLL": "27R", # Heathrow westerly preference (noise abatement / airspace flow)
    "EIDW": "28L", # Dublin main westerly
    "EINN": "24",  # Shannon main westerly
    "EGKK": "26L", # Gatwick main westerly
    "EGCC": "23R", # Manchester main westerly
    "EGSS": "22",  # Stansted main westerly
    "EGPF": "23",  # Glasgow main westerly
    "EGPH": "24",  # Edinburgh main westerly
    "EGAA": "25",  # Belfast main westerly
    "EGBB": "33",  # Birmingham
    "EICK": "16",  # Cork main
}

def parse_runway_heading(rwy: Dict[str, Any]) -> float:
    """
    Extracts magnetic/true runway heading in degrees (0-360).
    Checks 'trueBearing' / 'true_bearing' first, falling back to designator digits.
    """
    tb = rwy.get("trueBearing") or rwy.get("true_bearing") or ""
    if tb:
        m = re.search(r"(\d+(?:\.\d+)?)", str(tb))
        if m:
            val = float(m.group(1))
            if 0 <= val <= 360:
                return val

    # Fallback to designator digits (e.g. "27R" -> 270 deg, "09L" -> 90 deg)
    des = rwy.get("designator") or rwy.get("designation") or ""
    m = re.search(r"(\d{2})", str(des))
    if m:
        return float(int(m.group(1)) * 10)

    return 270.0 # Default westerly

def calculate_wind_components(rwy_hdg: float, wdir: Optional[int], wspd: Optional[int]) -> Tuple[float, float]:
    """
    Calculates headwind (positive) / tailwind (negative) and crosswind in knots.
    """
    if wdir is None or wspd is None or wspd == 0:
        return 0.0, 0.0

    delta_rad = math.radians(wdir - rwy_hdg)
    headwind = wspd * math.cos(delta_rad)
    crosswind = wspd * math.sin(delta_rad)
    return round(headwind, 1), round(crosswind, 1)

def get_metar(icao: str) -> Optional[Dict[str, Any]]:
    """
    Fetches real-time METAR from NOAA Aviation Weather API (https://aviationweather.gov/api/data/metar?ids={icao}&format=json).
    Caches results for 5 minutes.
    """
    icao_clean = icao.strip().upper()
    now = time.time()

    if icao_clean in _METAR_CACHE:
        cached = _METAR_CACHE[icao_clean]
        if now - cached["timestamp"] < CACHE_TTL_SEC:
            return cached["data"]

    url_json = f"https://aviationweather.gov/api/data/metar?ids={icao_clean}&format=json"
    req = urllib.request.Request(url_json, headers={"User-Agent": "FF-ICE-SWIM/2.0 (Aviation System)"})

    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data and isinstance(data, list) and len(data) > 0:
                item = data[0]
                wdir = item.get("wdir")
                try:
                    wdir_int = int(wdir) if wdir is not None and str(wdir).isdigit() else None
                except ValueError:
                    wdir_int = None

                wspd = item.get("wspd")
                wspd_int = int(wspd) if wspd is not None and str(wspd).isdigit() else 0

                metar_res = {
                    "icao": icao_clean,
                    "rawOb": item.get("rawOb", ""),
                    "reportTime": item.get("reportTime", ""),
                    "windDirection": wdir_int,
                    "windSpeedKnots": wspd_int,
                    "windGustKnots": item.get("wgst"),
                    "tempC": item.get("temp"),
                    "dewpointC": item.get("dewp"),
                    "altimeterHpa": item.get("altim"),
                    "flightCategory": item.get("fltcat", "VFR"),
                    "isVariableWind": wdir == "VRB" or item.get("wdir") == "VRB"
                }
                _METAR_CACHE[icao_clean] = {"timestamp": now, "data": metar_res}
                return metar_res
    except Exception as e:
        # Fallback to plain text endpoint if JSON fails
        pass

    # Fallback to plain text format
    try:
        url_text = f"https://aviationweather.gov/api/data/metar?ids={icao_clean}"
        req_text = urllib.request.Request(url_text, headers={"User-Agent": "FF-ICE-SWIM/2.0"})
        with urllib.request.urlopen(req_text, timeout=3) as resp:
            text = resp.read().decode("utf-8").strip()
            if text:
                # Parse wind regex e.g. 24015KT, VRB02KT
                wm = re.search(r"\b(VRB|\d{3})(\d{2,3})(?:G\d{2,3})?KT\b", text)
                wdir_int = None
                wspd_int = 0
                is_vrb = False
                if wm:
                    dir_str = wm.group(1)
                    if dir_str == "VRB":
                        is_vrb = True
                    else:
                        wdir_int = int(dir_str)
                    wspd_int = int(wm.group(2))

                metar_res = {
                    "icao": icao_clean,
                    "rawOb": text,
                    "reportTime": "",
                    "windDirection": wdir_int,
                    "windSpeedKnots": wspd_int,
                    "windGustKnots": None,
                    "tempC": None,
                    "dewpointC": None,
                    "altimeterHpa": None,
                    "flightCategory": "VFR",
                    "isVariableWind": is_vrb
                }
                _METAR_CACHE[icao_clean] = {"timestamp": now, "data": metar_res}
                return metar_res
    except Exception:
        pass

    return None

def get_taf(icao: str) -> Optional[Dict[str, Any]]:
    """
    Fetches real-time Terminal Aerodrome Forecast (TAF) from NOAA API.
    """
    icao_clean = icao.strip().upper()
    now = time.time()

    if icao_clean in _TAF_CACHE:
        cached = _TAF_CACHE[icao_clean]
        if now - cached["timestamp"] < 600:
            return cached["data"]

    url = f"https://aviationweather.gov/api/data/taf?ids={icao_clean}&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "FF-ICE-SWIM/2.0"})

    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data and isinstance(data, list) and len(data) > 0:
                item = data[0]
                taf_res = {
                    "icao": icao_clean,
                    "rawTAF": item.get("rawTAF", ""),
                    "issueTime": item.get("issueTime", ""),
                    "validTimeFrom": item.get("validTimeFrom"),
                    "validTimeTo": item.get("validTimeTo")
                }
                _TAF_CACHE[icao_clean] = {"timestamp": now, "data": taf_res}
                return taf_res
    except Exception:
        pass

    return None

def determine_active_runway(airport: Dict[str, Any], metar_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Selects the active operational runway into the wind based on NOAA METAR wind direction & speed.
    Evaluates headwind/crosswind components across all available runways.
    """
    icao = airport.get("icao", "")
    runways = airport.get("runways", [])

    if not runways:
        return {
            "activeRunway": "AUTO",
            "runwayHeading": 270.0,
            "headwindKnots": 0.0,
            "crosswindKnots": 0.0,
            "windSummary": "No runway data defined",
            "isCalmOrDefault": True,
            "rawMetar": ""
        }

    if metar_data is None:
        metar_data = get_metar(icao)

    wdir = metar_data.get("windDirection") if metar_data else None
    wspd = metar_data.get("windSpeedKnots", 0) if metar_data else 0
    is_vrb = metar_data.get("isVariableWind", False) if metar_data else True
    raw_metar = metar_data.get("rawOb", "") if metar_data else "METAR unavailable - Default Calm Applied"

    # If wind is calm (< 4 kts) or variable (VRB) or missing, check preferential calm-wind runway
    preferred_rwy_des = CALM_WIND_DEFAULTS.get(icao)

    scored_runways = []
    for r in runways:
        des = r.get("designator") or r.get("designation") or ""
        rwy_hdg = parse_runway_heading(r)
        hw, xw = calculate_wind_components(rwy_hdg, wdir, wspd)

        # Bonus preference if calm-wind default matches
        pref_score = 100.0 if (preferred_rwy_des and (preferred_rwy_des in des or des in preferred_rwy_des)) else 0.0

        # Primary score: headwind component (into the wind).
        # If calm/VRB, preferential score dominates.
        if is_vrb or wdir is None or wspd < 4:
            score = pref_score
        else:
            score = hw + (pref_score * 0.05) # Headwind is primary; slight bias to prefer primary runway in crosswind

        scored_runways.append({
            "designator": des,
            "heading": rwy_hdg,
            "headwind": hw,
            "crosswind": xw,
            "score": score,
            "runwayObj": r
        })

    # Sort descending by score
    scored_runways.sort(key=lambda s: s["score"], reverse=True)
    best = scored_runways[0]

    wind_desc = f"{wdir:03d}° at {wspd} kt" if (wdir is not None and not is_vrb) else f"VRB/{wspd} kt (Calm/Variable)"
    explanation = (
        f"Active runway {best['designator']} selected into wind ({wind_desc}): "
        f"Headwind {best['headwind']} kts, Crosswind {abs(best['crosswind'])} kts."
    )

    return {
        "activeRunway": best["designator"],
        "runwayHeading": best["heading"],
        "headwindKnots": best["headwind"],
        "crosswindKnots": best["crosswind"],
        "windSummary": wind_desc,
        "isCalmOrDefault": (is_vrb or wdir is None or wspd < 4),
        "rawMetar": raw_metar,
        "explanation": explanation,
        "allRunways": [
            {
                "designator": s["designator"],
                "heading": s["heading"],
                "headwind": s["headwind"],
                "crosswind": s["crosswind"],
                "isActive": s["designator"] == best["designator"]
            }
            for s in scored_runways
        ]
    }
