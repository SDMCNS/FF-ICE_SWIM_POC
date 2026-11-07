/**
 * Coordinate Parsing and Geodesy Utilities for FF-ICE & Aviation Geometries
 */

export interface LatLon {
  latitude: number;   // Decimal degrees, -90 to 90
  longitude: number;  // Decimal degrees, -180 to 180
}

/**
 * Parses a DMS latitude string (e.g. "512839N", "503011.88N", "532957.8N") into decimal degrees.
 */
export function parseDmsLatitude(str: string): number {
  const clean = str.trim().toUpperCase();
  // Pattern: 2 digits deg, 2 digits min, optional seconds (int or float), then N or S
  const match = clean.match(/^(\d{2})(\d{2})(?:(\d{2}(?:\.\d+)?))?\s*([NS])$/);
  if (match) {
    const deg = parseInt(match[1], 10);
    const min = parseInt(match[2], 10);
    const sec = match[3] ? parseFloat(match[3]) : 0;
    const hemisphere = match[4];
    let val = deg + min / 60 + sec / 3600;
    if (hemisphere === 'S') val = -val;
    return val;
  }

  // Fallback: check if it's already a decimal number
  const num = parseFloat(clean);
  if (!isNaN(num)) {
    return num;
  }

  throw new Error(`Invalid latitude format: "${str}"`);
}

/**
 * Parses a DMS longitude string (e.g. "0002741W", "0032833.64W", "0061825.6W", "0003558.49E") into decimal degrees.
 */
export function parseDmsLongitude(str: string): number {
  const clean = str.trim().toUpperCase();
  // Pattern: 3 digits deg (or sometimes 2 or 3), 2 digits min, optional seconds, then E or W
  const match = clean.match(/^(\d{2,3})(\d{2})(?:(\d{2}(?:\.\d+)?))?\s*([EW])$/);
  if (match) {
    const deg = parseInt(match[1], 10);
    const min = parseInt(match[2], 10);
    const sec = match[3] ? parseFloat(match[3]) : 0;
    const hemisphere = match[4];
    let val = deg + min / 60 + sec / 3600;
    if (hemisphere === 'W') val = -val;
    return val;
  }

  // Fallback: check if it's already a decimal number
  const num = parseFloat(clean);
  if (!isNaN(num)) {
    return num;
  }

  throw new Error(`Invalid longitude format: "${str}"`);
}

/**
 * Parses combined coordinate string (e.g. "532517N 0061612W") or separate inputs.
 */
export function parseCoordinates(latOrCombined: string, lon?: string): LatLon {
  if (lon !== undefined && lon !== null && lon.trim() !== '') {
    return {
      latitude: parseDmsLatitude(latOrCombined),
      longitude: parseDmsLongitude(lon)
    };
  }

  const parts = latOrCombined.trim().split(/\s+/);
  if (parts.length === 2) {
    return {
      latitude: parseDmsLatitude(parts[0]),
      longitude: parseDmsLongitude(parts[1])
    };
  }

  throw new Error(`Cannot parse coordinate string: "${latOrCombined}"`);
}

/**
 * Formats decimal coordinates into standard ICAO / FIXM DMS format.
 * Latitude: DDMMSS[N/S], Longitude: DDDMMSS[E/W]
 */
export function formatDms(coords: LatLon): { latitude: string; longitude: string; combined: string } {
  const latHemi = coords.latitude >= 0 ? 'N' : 'S';
  const absLat = Math.abs(coords.latitude);
  const latDeg = Math.floor(absLat);
  const latMin = Math.floor((absLat - latDeg) * 60);
  const latSec = Math.round(((absLat - latDeg) * 60 - latMin) * 60);
  const latStr = `${String(latDeg).padStart(2, '0')}${String(latMin).padStart(2, '0')}${String(latSec).padStart(2, '0')}${latHemi}`;

  const lonHemi = coords.longitude >= 0 ? 'E' : 'W';
  const absLon = Math.abs(coords.longitude);
  const lonDeg = Math.floor(absLon);
  const lonMin = Math.floor((absLon - lonDeg) * 60);
  const lonSec = Math.round(((absLon - lonDeg) * 60 - lonMin) * 60);
  const lonStr = `${String(lonDeg).padStart(3, '0')}${String(lonMin).padStart(2, '0')}${String(lonSec).padStart(2, '0')}${lonHemi}`;

  return {
    latitude: latStr,
    longitude: lonStr,
    combined: `${latStr} ${lonStr}`
  };
}

/**
 * Parses elevation string (e.g. "83 FT", "243 ft AMSL", "268 FT") to feet integer.
 */
export function parseElevationFeet(elevationStr?: string | null): number {
  if (!elevationStr) return 0;
  // If explicitly in feet (e.g. "243 ft", "83 FT", "83 FT AMSL")
  const ftMatch = elevationStr.match(/(\d+(?:\.\d+)?)\s*(?:FT|FEET)\b/i);
  if (ftMatch) {
    return Math.round(parseFloat(ftMatch[1]));
  }

  // If in meters (e.g. "50 M", "120 METRES")
  const mMatch = elevationStr.match(/(\d+(?:\.\d+)?)\s*(?:M|METRES|METER|METERS)\b/i);
  if (mMatch) {
    return Math.round(parseFloat(mMatch[1]) * 3.28084);
  }

  // Generic number fallback
  const numMatch = elevationStr.match(/(\d+(?:\.\d+)?)/);
  if (numMatch) {
    return Math.round(parseFloat(numMatch[1]));
  }
  return 0;
}
