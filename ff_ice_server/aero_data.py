"""
Aeronautical Data Ingestion & Geodesy in Python for FF-ICE UK/Irish Airspace.
"""
import os
import re
import csv
import json
import math
from typing import Dict, List, Optional, Tuple, Any

EARTH_RADIUS_NM = 3440.065

def parse_dms_lat(s: str) -> float:
    s = str(s).strip().upper()
    has_minus = s.startswith("-")
    clean = s.lstrip("+-")
    m = re.match(r"^(\d{2})(\d{2})(?:(\d{2}(?:\.\d+)?))?\s*([NS])$", clean)
    if m:
        deg = int(m.group(1))
        minute = int(m.group(2))
        sec = float(m.group(3)) if m.group(3) else 0.0
        val = deg + minute / 60.0 + sec / 3600.0
        return -val if m.group(4) == 'S' or has_minus else val
    try:
        return float(s)
    except ValueError:
        raise ValueError(f"Cannot parse latitude: {s}")

def parse_dms_lon(s: str) -> float:
    s = str(s).strip().upper()
    has_minus = s.startswith("-")
    clean = s.lstrip("+-")
    m = re.match(r"^(\d{2,3})(\d{2})(?:(\d{2}(?:\.\d+)?))?\s*([EW])$", clean)
    if m:
        deg = int(m.group(1))
        minute = int(m.group(2))
        sec = float(m.group(3)) if m.group(3) else 0.0
        val = deg + minute / 60.0 + sec / 3600.0
        return -val if m.group(4) == 'W' or has_minus else val
    try:
        return float(s)
    except ValueError:
        raise ValueError(f"Cannot parse longitude: {s}")

def parse_coordinates(lat_or_combined: str, lon: Optional[str] = None) -> Tuple[float, float]:
    if lon:
        return parse_dms_lat(lat_or_combined), parse_dms_lon(lon)
    parts = lat_or_combined.strip().split()
    if len(parts) == 2:
        return parse_dms_lat(parts[0]), parse_dms_lon(parts[1])
    raise ValueError(f"Cannot parse coordinate: {lat_or_combined}")

def haversine_distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_RADIUS_NM * c

def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)

    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    theta = math.atan2(y, x)
    return (math.degrees(theta) + 360.0) % 360.0

def interpolate_point(lat1: float, lon1: float, lat2: float, lon2: float, fraction: float) -> Tuple[float, float]:
    if fraction <= 0: return lat1, lon1
    if fraction >= 1: return lat2, lon2

    phi1 = math.radians(lat1)
    lambda1 = math.radians(lon1)
    phi2 = math.radians(lat2)
    lambda2 = math.radians(lon2)

    dist = haversine_distance_nm(lat1, lon1, lat2, lon2) / EARTH_RADIUS_NM
    if dist == 0: return lat1, lon1

    a = math.sin((1 - fraction) * dist) / math.sin(dist)
    b = math.sin(fraction * dist) / math.sin(dist)

    x = a * math.cos(phi1) * math.cos(lambda1) + b * math.cos(phi2) * math.cos(lambda2)
    y = a * math.cos(phi1) * math.sin(lambda1) + b * math.cos(phi2) * math.sin(lambda2)
    z = a * math.sin(phi1) + b * math.sin(phi2)

    phi = math.atan2(z, math.sqrt(x*x + y*y))
    lam = math.atan2(y, x)
    return math.degrees(phi), math.degrees(lam)

def is_point_in_polygon(lat: float, lon: float, polygon: List[Tuple[float, float]]) -> bool:
    inside = False
    n = len(polygon)
    for i in range(n):
        j = (i - 1 + n) % n
        xi, yi = polygon[i][1], polygon[i][0] # lon, lat
        xj, yj = polygon[j][1], polygon[j][0]

        intersect = ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi)
        if intersect:
            inside = not inside
    return inside

class AeroDataStore:
    def __init__(self, base_dir: str = "."):
        self.base_dir = os.path.abspath(base_dir)
        self.airports: Dict[str, Dict[str, Any]] = {}
        self.waypoints: Dict[str, Dict[str, Any]] = {}
        self.routes: Dict[str, Dict[str, Any]] = {}
        self.firs: Dict[str, Dict[str, Any]] = {}
        self.load_all()

    def load_all(self):
        self._load_airports()
        self._load_waypoints()
        self._load_routes()
        self._load_firs()

    def rebuild(self, base_dir: Optional[str] = None):
        """
        Dynamically clears and re-ingests all aeronautical datasets (airports, waypoints,
        routes, FIR boundaries) across any geographic region or country.
        """
        if base_dir:
            self.base_dir = os.path.abspath(base_dir)
        self.airports.clear()
        self.waypoints.clear()
        self.routes.clear()
        self.firs.clear()
        self.load_all()

    def _parse_airport_dict(self, data: Dict[str, Any], filename: str = "") -> Optional[Dict[str, Any]]:
        """
        Universal, location-agnostic aerodrome parser for UK, Irish, European, US,
        and international ICAO/FAA AIP formats.
        """
        if not isinstance(data, dict):
            return None

        # 1. Determine 4-letter ICAO code
        icao = (
            data.get("icao_code")
            or data.get("aerodrome_identifier")
            or data.get("icao")
            or data.get("ident")
            or (data.get("aerodrome") if isinstance(data.get("aerodrome"), dict) else {}).get("indicator")
        )
        if not icao and isinstance(data.get("aerodrome"), str):
            m = re.search(r"\(([A-Z]{4})\)", data.get("aerodrome", ""))
            if m: icao = m.group(1)
        if not icao:
            m = re.search(r"\b([A-Z]{4})\b", filename)
            if m: icao = m.group(1)
        if not icao:
            return None

        icao = str(icao).strip().upper()

        # 2. Extract ARP coordinates
        lat, lon = None, None
        arp = data.get("arp_coordinates") or data.get("coordinates")
        if not arp and "geographical_and_administrative_data" in data:
            arp = data["geographical_and_administrative_data"].get("arp_coordinates")
        if not arp and "geographical_and_administrative" in data:
            arp = data["geographical_and_administrative"].get("arp_coordinates")
        if not arp and isinstance(data.get("aerodrome"), dict):
            arp = data["aerodrome"].get("geographical_and_administrative", {}).get("arp_coordinates")

        if isinstance(arp, dict):
            if "latitude" in arp and "longitude" in arp:
                try:
                    lat, lon = parse_coordinates(str(arp["latitude"]), str(arp["longitude"]))
                except Exception:
                    pass
        elif isinstance(arp, str) and arp.strip():
            try:
                lat, lon = parse_coordinates(arp)
            except Exception:
                pass

        if lat is None:
            if "latitude" in data and "longitude" in data:
                try:
                    lat = float(data["latitude"])
                    lon = float(data["longitude"])
                except Exception:
                    pass

        if lat is None or lon is None:
            return None

        # 3. Extract Aerodrome Elevation (feet)
        elev_str = str(
            data.get("elevation")
            or data.get("elevationFeet")
            or data.get("geographical_and_administrative_data", {}).get("elevation_reference_temperature_mean_low")
            or data.get("geographical_and_administrative", {}).get("elevation")
            or (data.get("aerodrome") if isinstance(data.get("aerodrome"), dict) else {}).get("geographical_and_administrative", {}).get("elevation")
            or "0"
        )
        m = re.search(r"(\d+)", elev_str)
        elev = int(m.group(1)) if m else 0

        # 4. Extract Aerodrome Name
        name = (
            data.get("name")
            or (data.get("aerodrome") if isinstance(data.get("aerodrome"), str) else None)
            or (data.get("aerodrome") if isinstance(data.get("aerodrome"), dict) else {}).get("name")
            or icao
        )
        name = re.sub(r"\s*\([A-Z]{4}\)", "", str(name)).strip()

        # 5. Extract Runways
        raw_rwys = (
            data.get("runways")
            or data.get("runway_physical_characteristics")
            or (data.get("aerodrome") if isinstance(data.get("aerodrome"), dict) else {}).get("runways")
            or []
        )
        runways = []
        if isinstance(raw_rwys, list):
            for r in raw_rwys:
                if isinstance(r, dict):
                    des = r.get("designation") or r.get("designator") or r.get("ident")
                    if des and not any(existing["designator"] == des for existing in runways):
                        runways.append({
                            "designator": str(des).strip().upper(),
                            "trueBearing": r.get("true_bearing") or r.get("bearing"),
                            "dimensions": r.get("dimensions") or r.get("length_width"),
                            "surface": r.get("surface") or r.get("strength_and_surface")
                        })

        # 6. Extract Country
        country = data.get("country")
        if not country:
            if icao.startswith("EI"): country = "IE"
            elif icao.startswith("EG"): country = "GB"
            elif icao.startswith("LF"): country = "FR"
            elif icao.startswith("ED"): country = "DE"
            elif icao.startswith("EH"): country = "NL"
            elif icao.startswith("K"): country = "US"
            else: country = icao[:2]

        return {
            "icao": icao,
            "name": name,
            "country": country,
            "latitude": lat,
            "longitude": lon,
            "elevationFeet": elev,
            "runways": runways
        }

    def _load_airports(self):
        airports_dir = os.path.join(self.base_dir, "airports")
        if os.path.isdir(airports_dir):
            for fname in os.listdir(airports_dir):
                fpath = os.path.join(airports_dir, fname)
                if not os.path.isfile(fpath): continue

                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    parsed = self._parse_airport_dict(data, filename=fname)
                    if parsed:
                        self.airports[parsed["icao"]] = parsed
                except Exception:
                    pass

        # Also check root directory for standalone airport files (e.g. EGLL.txt)
        for fname in os.listdir(self.base_dir):
            if fname.endswith(".txt") or fname.endswith(".json"):
                fpath = os.path.join(self.base_dir, fname)
                if not os.path.isfile(fpath): continue
                # Match typical 4-letter ICAO names in root (e.g. EGLL.txt, EIDW.json)
                if re.match(r"^[A-Z]{4}\.(txt|json)$", fname, re.I):
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        parsed = self._parse_airport_dict(data, filename=fname)
                        if parsed and parsed["icao"] not in self.airports:
                            self.airports[parsed["icao"]] = parsed
                    except Exception:
                        pass

    def _load_waypoints(self):
        """
        Universal waypoint loader: scans ALL files in Waypoints/ directory,
        parsing JSON arrays, JSON dictionaries, and CSV files from any country or FIR.
        """
        wp_dir = os.path.join(self.base_dir, "Waypoints")
        if not os.path.isdir(wp_dir): return

        for fname in sorted(os.listdir(wp_dir)):
            fpath = os.path.join(wp_dir, fname)
            if not os.path.isfile(fpath): continue

            # 1. JSON / Structured text files
            if fname.endswith(".json") or fname.endswith(".txt"):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    items = data if isinstance(data, list) else data.get("waypoints", [])
                    if isinstance(items, list):
                        for item in items:
                            if not isinstance(item, dict): continue
                            name = (
                                item.get("name_code_designator")
                                or item.get("name")
                                or item.get("ident")
                                or item.get("id")
                            )
                            if not name: continue
                            name = str(name).strip().upper()
                            if name in self.waypoints: continue

                            # Coordinates
                            c = item.get("coordinates")
                            lat, lon = None, None
                            if isinstance(c, dict) and "latitude" in c and "longitude" in c:
                                try:
                                    lat, lon = parse_coordinates(str(c["latitude"]), str(c["longitude"]))
                                except Exception:
                                    pass
                            elif isinstance(c, str):
                                try:
                                    lat, lon = parse_coordinates(c)
                                except Exception:
                                    pass
                            elif "latitude" in item and "longitude" in item:
                                try:
                                    lat, lon = float(item["latitude"]), float(item["longitude"])
                                except Exception:
                                    pass

                            if lat is None or lon is None: continue

                            country = item.get("country")
                            if not country:
                                country = "IE" if "IE" in fname.upper() else ("GB" if "UK" in fname.upper() else "XX")

                            details = item.get("details") or item.get("remarks") or item.get("ats_route_or_other_route")
                            self.waypoints[name] = {
                                "name": name,
                                "country": country,
                                "latitude": lat,
                                "longitude": lon,
                                "details": details
                            }
                except Exception:
                    pass

            # 2. CSV files
            elif fname.endswith(".csv"):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            name = row.get("name") or row.get("ident") or row.get("id")
                            if not name: continue
                            name = name.strip().upper()
                            if name in self.waypoints: continue
                            lat_val = row.get("lat") or row.get("latitude")
                            lon_val = row.get("lon") or row.get("longitude")
                            if lat_val and lon_val:
                                try:
                                    lat, lon = float(lat_val), float(lon_val)
                                    self.waypoints[name] = {
                                        "name": name,
                                        "country": row.get("country", "XX"),
                                        "latitude": lat,
                                        "longitude": lon,
                                        "details": row.get("details", "")
                                    }
                                except Exception:
                                    pass
                except Exception:
                    pass

    def _load_routes(self):
        routes_file = os.path.join(self.base_dir, "routes.txt")
        if not os.path.exists(routes_file): return
        try:
            with open(routes_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                des = item.get("route_designator")
                if not des: continue
                wps = []
                for w in item.get("waypoints", []):
                    try:
                        lat, lon = parse_coordinates(w.get("coordinates", ""))
                        wps.append({"name": w.get("name"), "latitude": lat, "longitude": lon})
                    except Exception:
                        pass
                self.routes[des] = {
                    "routeDesignator": des,
                    "navigationSpecification": item.get("navigation_specification", "RNAV 5"),
                    "waypoints": wps
                }
        except Exception:
            pass

    def _load_firs(self):
        fir_file = os.path.join(self.base_dir, "FIR", "FIR.csv")
        if not os.path.exists(fir_file): return

        rows_by_id: Dict[str, List[Dict[str, Any]]] = {}
        with open(fir_file, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or len(row) < 6: continue
                airspace_id = row[0].replace('"', '').strip()
                if not airspace_id:
                    continue
                try:
                    min_fl = int(row[1].replace('"', '').strip())
                    max_fl = int(row[2].replace('"', '').strip())
                    seq = int(row[3].replace('"', '').strip())
                    lat = float(row[4].replace('"', '').strip())
                    lon = float(row[5].replace('"', '').strip())
                except ValueError:
                    continue

                if airspace_id not in rows_by_id:
                    rows_by_id[airspace_id] = []
                rows_by_id[airspace_id].append({
                    "min_fl": min_fl, "max_fl": max_fl, "seq": seq, "lat": lat, "lon": lon
                })

        for airspace_id, rows in rows_by_id.items():
            rows.sort(key=lambda r: r["seq"])
            verts = [{"latitude": r["lat"], "longitude": r["lon"]} for r in rows]
            country = "IE" if airspace_id.startswith("EI") else ("GB" if airspace_id.startswith("EG") else airspace_id[:2])
            self.firs[airspace_id] = {
                "airspaceId": airspace_id,
                "country": country,
                "minFlightLevel": rows[0]["min_fl"],
                "maxFlightLevel": rows[0]["max_fl"],
                "vertices": verts
            }

    def search_airports(self, query: str = "", limit: int = 20) -> List[Dict[str, Any]]:
        q = query.strip().upper()
        res = []
        for a in self.airports.values():
            if not q or q in a["icao"] or q in a["name"].upper():
                res.append(a)
                if len(res) >= limit: break
        return res

    def search_waypoints(self, query: str = "", limit: int = 30) -> List[Dict[str, Any]]:
        q = query.strip().upper()
        res = []
        for w in self.waypoints.values():
            if not q or q in w["name"]:
                res.append(w)
                if len(res) >= limit: break
        return res

