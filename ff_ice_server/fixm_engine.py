"""
FIXM v4.2+ & iFIXM XML & JSON Engine in Python for FF-ICE Flight Plans.
Supports both strict Core FIXM (XSD-compliant) and FF-ICE Release 1 / 2 structures.
"""
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

WAKE_TO_FIXM_ENUM = {
    "M": "MEDIUM",
    "H": "HEAVY",
    "L": "LIGHT",
    "J": "SUPER"
}

FIXM_ENUM_TO_WAKE = {
    "MEDIUM": "M",
    "HEAVY": "H",
    "LIGHT": "L",
    "SUPER": "J"
}

def generate_gufi() -> str:
    return str(uuid.uuid4())

def serialize_to_fixm_xml(plan: Dict[str, Any]) -> str:
    gufi = plan.get("gufi") or generate_gufi()
    clean_gufi = gufi.replace("urn:uuid:", "").strip()
    flight_id = plan.get("flightIdentification", {})
    aircraft = plan.get("aircraft", {})
    caps = aircraft.get("capabilities", {})
    dep = plan.get("departure", {})
    arr = plan.get("arrival", {})
    en_route = plan.get("enRoute", {})
    traj = plan.get("trajectory", {})
    points = traj.get("points4D", [])

    wake_code = aircraft.get("wakeTurbulence") or aircraft.get("wakeTurbulenceCategory", "M")
    wake_code = wake_code.upper()[:1] if wake_code else "M"
    wake_enum = WAKE_TO_FIXM_ENUM.get(wake_code, "MEDIUM")

    points_xml_list = []
    for p in points:
        c = p.get("coordinates", {})
        points_xml_list.append(f"""        <fx:element>
          <fx:point4D>
            <fx:pointType>{p.get("pointType", "WAYPOINT")}</fx:pointType>
            <fx:pointIdentifier>{p.get("identifier", "WPT")}</fx:pointIdentifier>
            <fx:position>
              <fb:pos>{c.get("latitude", 0.0):.6f} {c.get("longitude", 0.0):.6f}</fb:pos>
            </fx:position>
            <fx:level>
              <fb:altitude uom="FT">{p.get("altitudeFeet", 0)}</fb:altitude>
              <fb:flightLevel>F{p.get("flightLevel", 0):03d}</fb:flightLevel>
            </fx:level>
            <fx:time>
              <fb:estimatedTime>{p.get("estimatedTimestamp", "")}</fb:estimatedTime>
              <fb:elapsedSeconds>{p.get("cumulativeTimeSeconds", 0)}</fb:elapsedSeconds>
            </fx:time>
            <fx:cumulativeDistance uom="NM">{p.get("cumulativeDistanceNm", 0.0)}</fx:cumulativeDistance>
            {f'<fx:airspace>{p.get("associatedAirspace")}</fx:airspace>' if p.get("associatedAirspace") else ''}
          </fx:point4D>
        </fx:element>""")

    points_xml = "\n".join(points_xml_list)

    dep_rwy_xml = f"""    <fx:runway>
      <fb:runwayDirectionDesignator>{dep.get("runway")}</fb:runwayDirectionDesignator>
    </fx:runway>""" if dep.get("runway") else ""

    arr_rwy_xml = f"""    <fx:runway>
      <fb:runwayDirectionDesignator>{arr.get("runway")}</fb:runwayDirectionDesignator>
    </fx:runway>""" if arr.get("runway") else ""

    reg_xml = f"""    <fx:aircraftRegistration>{flight_id.get("aircraftRegistration")}</fx:aircraftRegistration>""" if flight_id.get("aircraftRegistration") else ""

    # Runway & off-block timing elements (EOBT vs ETOT, Taxi Out/In)
    eobt_val = dep.get("estimatedOffBlockTime") or dep.get("eobt") or ""
    etot_val = dep.get("estimatedTakeOffTime") or dep.get("etot") or ""
    taxi_out_min = dep.get("taxiOutMinutes") or dep.get("exot")
    taxi_out_xml = f"""    <fx:taxiOut>
      <fb:duration>PT{int(taxi_out_min)}M</fb:duration>
    </fx:taxiOut>""" if taxi_out_min else ""

    etot_xml = f"""    <fx:takeOff>
      <fb:estimatedTime>{etot_val}</fb:estimatedTime>
    </fx:takeOff>
    <fx:estimatedTakeOffTime>{etot_val}</fx:estimatedTakeOffTime>""" if etot_val else ""

    eta_val = arr.get("estimatedTimeOfArrival") or arr.get("eta") or arr.get("eldt") or ""
    eibt_val = arr.get("estimatedInBlockTime") or arr.get("eibt") or ""
    taxi_in_min = arr.get("taxiInMinutes") or arr.get("exit")
    taxi_in_xml = f"""    <fx:taxiIn>
      <fb:duration>PT{int(taxi_in_min)}M</fb:duration>
    </fx:taxiIn>""" if taxi_in_min else ""

    eibt_xml = f"""    <fx:inBlock>
      <fb:estimatedTime>{eibt_val}</fb:estimatedTime>
    </fx:inBlock>
    <fx:estimatedInBlockTime>{eibt_val}</fx:estimatedInBlockTime>""" if eibt_val else ""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<fx:Flight xmlns:fx="http://www.fixm.aero/flight/4.2"
           xmlns:fb="http://www.fixm.aero/base/4.2"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <fx:gufi codeSpace="urn:uuid">urn:uuid:{clean_gufi}</fx:gufi>
  <fx:flightStatus>{plan.get("status", "FILED")}</fx:flightStatus>
  <fx:messageType>{plan.get("messageType", "FILING")}</fx:messageType>
  <fx:filingTime>{plan.get("filingTime", datetime.now(timezone.utc).isoformat() + "Z")}</fx:filingTime>

  <fx:flightIdentification>
    <fx:aircraftIdentification>{flight_id.get("aircraftIdentification", "UNKNOWN")}</fx:aircraftIdentification>
{reg_xml}
  </fx:flightIdentification>

  <fx:aircraft>
    <fx:aircraftType>{aircraft.get("aircraftType", "A320")}</fx:aircraftType>
    <fx:type>
      <fb:icaoAircraftTypeDesignator>{aircraft.get("aircraftType", "A320")}</fb:icaoAircraftTypeDesignator>
    </fx:type>
    <fx:wakeTurbulence>{wake_enum}</fx:wakeTurbulence>
    <fx:wakeTurbulenceCategory>{wake_code}</fx:wakeTurbulenceCategory>
    <fx:capabilities>
      <fx:standardEquipment>{caps.get("standardEquipment", "SDFGIRW/LB1")}</fx:standardEquipment>
    </fx:capabilities>
  </fx:aircraft>

  <fx:departure>
    <fx:aerodrome>
      <fb:locationIndicator>{dep.get("aerodrome", "")}</fb:locationIndicator>
    </fx:aerodrome>
{dep_rwy_xml}
    <fx:elevation uom="FT">{dep.get("elevationFeet", 0)}</fx:elevation>
    <fx:offBlock>
      <fb:estimatedTime>{eobt_val}</fb:estimatedTime>
    </fx:offBlock>
    <fx:estimatedOffBlockTime>{eobt_val}</fx:estimatedOffBlockTime>
{etot_xml}
{taxi_out_xml}
  </fx:departure>

  <fx:arrival>
    <fx:destination>
      <fb:locationIndicator>{arr.get("aerodrome", "")}</fb:locationIndicator>
    </fx:destination>
    <fx:aerodrome>{arr.get("aerodrome", "")}</fx:aerodrome>
{arr_rwy_xml}
    <fx:elevation uom="FT">{arr.get("elevationFeet", 0)}</fx:elevation>
    <fx:touchdown>
      <fb:estimatedTime>{eta_val}</fb:estimatedTime>
    </fx:touchdown>
    <fx:estimatedTimeOfArrival>{eta_val}</fx:estimatedTimeOfArrival>
{eibt_xml}
{taxi_in_xml}
  </fx:arrival>

  <fx:enRoute>
    <fx:cruisingLevel>
      <fb:flightLevel>{en_route.get("cruisingLevel", "F280")}</fb:flightLevel>
    </fx:cruisingLevel>
    <fx:cruisingSpeed uom="KT">{en_route.get("cruisingSpeed", "N0450")}</fx:cruisingSpeed>
    <fx:routeString>{en_route.get("routeString", "")}</fx:routeString>
  </fx:enRoute>

  <fx:routeTrajectory>
    <fx:trajectoryProfile>
      <fx:totalDistance uom="NM">{traj.get("totalDistanceNm", 0.0)}</fx:totalDistance>
      <fx:totalFlightTimeMinutes>{traj.get("totalFlightTimeMinutes", 0.0)}</fx:totalFlightTimeMinutes>
      <fx:agreedTrajectory>
{points_xml}
      </fx:agreedTrajectory>
    </fx:trajectoryProfile>
  </fx:routeTrajectory>
</fx:Flight>"""

def parse_fixm_xml(xml_content: str) -> Dict[str, Any]:
    """
    Parses FIXM XML string into standard FF-ICE dictionary.
    Handles namespace prefixes and both nested and flat structures.
    """
    root = ET.fromstring(xml_content)
    # Strip namespaces for easy tag matching
    for elem in root.iter():
        if '}' in elem.tag:
            elem.tag = elem.tag.split('}', 1)[1]

    gufi_elem = root.find("gufi")
    raw_gufi = gufi_elem.text if gufi_elem is not None and gufi_elem.text else generate_gufi()
    gufi = raw_gufi.replace("urn:uuid:", "").strip()

    callsign = "UNKNOWN"
    fl_id = root.find("flightIdentification")
    if fl_id is not None:
        call_el = fl_id.find("aircraftIdentification")
        if call_el is not None and call_el.text:
            callsign = call_el.text.strip()

    ac_type = "A320"
    wake = "M"
    ac_elem = root.find("aircraft")
    if ac_elem is not None:
        t_el = ac_elem.find(".//icaoAircraftTypeDesignator")
        if t_el is None:
            t_el = ac_elem.find("aircraftType")
        if t_el is not None and t_el.text:
            ac_type = t_el.text.strip()

        w_el = ac_elem.find("wakeTurbulence")
        if w_el is None:
            w_el = ac_elem.find("wakeTurbulenceCategory")
        if w_el is not None and w_el.text:
            raw_w = w_el.text.strip().upper()
            wake = FIXM_ENUM_TO_WAKE.get(raw_w, raw_w[:1])

    dep_elem = root.find("departure")
    dep_icao = ""
    eobt = ""
    etot = ""
    dep_elev = 0
    taxi_out_min = None
    if dep_elem is not None:
        loc = dep_elem.find(".//locationIndicator")
        if loc is not None and loc.text:
            dep_icao = loc.text.strip()
        elif dep_elem.find("aerodrome") is not None and dep_elem.find("aerodrome").text:
            dep_icao = dep_elem.find("aerodrome").text.strip()

        e_time = dep_elem.find(".//offBlock/estimatedTime")
        if e_time is None:
            e_time = dep_elem.find("estimatedOffBlockTime")
        if e_time is not None and e_time.text:
            eobt = e_time.text.strip()

        t_time = dep_elem.find(".//takeOff/estimatedTime")
        if t_time is None:
            t_time = dep_elem.find("estimatedTakeOffTime")
        if t_time is not None and t_time.text:
            etot = t_time.text.strip()

        dur_el = dep_elem.find(".//taxiOut/duration")
        if dur_el is not None and dur_el.text:
            # parse PT15M format
            raw_dur = dur_el.text.strip().replace("PT", "").replace("M", "")
            try: taxi_out_min = int(raw_dur)
            except ValueError: pass

        elev = dep_elem.find(".//elevation")
        if elev is not None and elev.text:
            try: dep_elev = int(elev.text)
            except ValueError: dep_elev = 0

    arr_elem = root.find("arrival")
    arr_icao = ""
    eta = ""
    eibt = ""
    arr_elev = 0
    taxi_in_min = None
    if arr_elem is not None:
        loc = arr_elem.find(".//locationIndicator")
        if loc is not None and loc.text:
            arr_icao = loc.text.strip()
        elif arr_elem.find("destination") is not None and arr_elem.find("destination").text:
            arr_icao = arr_elem.find("destination").text.strip()
        elif arr_elem.find("aerodrome") is not None and arr_elem.find("aerodrome").text:
            arr_icao = arr_elem.find("aerodrome").text.strip()

        a_time = arr_elem.find(".//touchdown/estimatedTime")
        if a_time is None:
            a_time = arr_elem.find("estimatedTimeOfArrival")
        if a_time is not None and a_time.text:
            eta = a_time.text.strip()

        ib_time = arr_elem.find(".//inBlock/estimatedTime")
        if ib_time is None:
            ib_time = arr_elem.find("estimatedInBlockTime")
        if ib_time is not None and ib_time.text:
            eibt = ib_time.text.strip()

        dur_in_el = arr_elem.find(".//taxiIn/duration")
        if dur_in_el is not None and dur_in_el.text:
            raw_dur_in = dur_in_el.text.strip().replace("PT", "").replace("M", "")
            try: taxi_in_min = int(raw_dur_in)
            except ValueError: pass

        elev = arr_elem.find(".//elevation")
        if elev is not None and elev.text:
            try: arr_elev = int(elev.text)
            except ValueError: arr_elev = 0

    points_4d = []
    agreed = root.find(".//agreedTrajectory")
    if agreed is not None:
        for pt_el in agreed.findall(".//point4D"):
            pt_type = pt_el.find("pointType").text if pt_el.find("pointType") is not None else "WAYPOINT"
            ident = pt_el.find("pointIdentifier").text if pt_el.find("pointIdentifier") is not None else "WPT"

            lat, lon = 0.0, 0.0
            pos_el = pt_el.find(".//pos")
            if pos_el is not None and pos_el.text:
                parts = pos_el.text.strip().split()
                if len(parts) >= 2:
                    lat, lon = float(parts[0]), float(parts[1])

            alt_ft = int(pt_el.find(".//altitude").text) if pt_el.find(".//altitude") is not None and pt_el.find(".//altitude").text else 0
            fl_text = pt_el.find(".//flightLevel").text if pt_el.find(".//flightLevel") is not None and pt_el.find(".//flightLevel").text else "F000"
            fl = int(fl_text.replace("F", "").replace("f", "")) if any(c.isdigit() for c in fl_text) else 0

            time_str = pt_el.find(".//estimatedTime").text if pt_el.find(".//estimatedTime") is not None else ""
            dist = float(pt_el.find(".//cumulativeDistance").text) if pt_el.find(".//cumulativeDistance") is not None and pt_el.find(".//cumulativeDistance").text else 0.0

            points_4d.append({
                "pointType": pt_type,
                "identifier": ident,
                "coordinates": {"latitude": lat, "longitude": lon},
                "altitudeFeet": alt_ft,
                "flightLevel": fl,
                "cumulativeDistanceNm": dist,
                "groundSpeedKnots": 450,
                "cumulativeTimeSeconds": 0,
                "estimatedTimestamp": time_str,
                "pointSource": "CALCULATED"
            })

    return {
        "gufi": gufi,
        "status": root.find("flightStatus").text if root.find("flightStatus") is not None else "FILED",
        "messageType": root.find("messageType").text if root.find("messageType") is not None else "FILING",
        "flightIdentification": {"aircraftIdentification": callsign},
        "aircraft": {"aircraftType": ac_type, "wakeTurbulence": wake},
        "departure": {
            "aerodrome": dep_icao,
            "estimatedOffBlockTime": eobt,
            "eobt": eobt,
            "estimatedTakeOffTime": etot,
            "etot": etot,
            "taxiOutMinutes": taxi_out_min,
            "elevationFeet": dep_elev
        },
        "arrival": {
            "aerodrome": arr_icao,
            "estimatedTimeOfArrival": eta,
            "eldt": eta,
            "estimatedInBlockTime": eibt,
            "eibt": eibt,
            "taxiInMinutes": taxi_in_min,
            "elevationFeet": arr_elev
        },
        "trajectory": {"points4D": points_4d}
    }
