/**
 * 2D and 3D Airspace & FIR Spatial Geometry Algorithms
 */
import { LatLon } from './coordinates.js';
import { calculateDistanceNm, interpolateIntermediatePoint } from './distance.js';

export interface AirspacePolygon {
  airspaceId: string;
  minFlightLevel: number; // e.g. 0 (SFC) or 245
  maxFlightLevel: number; // e.g. 245 or 999 (UNL)
  vertices: LatLon[];
}

export interface FirCrossing {
  airspaceId: string;
  entryPoint: LatLon;
  entryFraction: number;    // 0..1 along the leg
  distanceFromStartNm: number;
  flightLevel: number;
}

/**
 * Checks if a point (lat, lon) is inside a 2D polygon using standard ray-casting.
 */
export function isPointInPolygon(point: LatLon, polygon: LatLon[]): boolean {
  let inside = false;
  const x = point.longitude;
  const y = point.latitude;

  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i].longitude;
    const yi = polygon[i].latitude;
    const xj = polygon[j].longitude;
    const yj = polygon[j].latitude;

    const intersect = ((yi > y) !== (yj > y)) &&
      (x < (xj - xi) * (y - yi) / (yj - yi) + xi);

    if (intersect) {
      inside = !inside;
    }
  }

  return inside;
}

/**
 * Checks if an altitude (in feet) is within the vertical limits of an airspace.
 * Flight Level to feet conversion: FL * 100 ft (e.g. FL245 = 24,500 ft).
 */
export function isAltitudeInAirspace(altitudeFeet: number, minFL: number, maxFL: number): boolean {
  const minFeet = minFL * 100;
  const maxFeet = maxFL * 100;
  return altitudeFeet >= minFeet && altitudeFeet <= maxFeet;
}

/**
 * Checks 3D containment of a 3D point (lat, lon, altitudeFt) in an AirspacePolygon.
 */
export function isPointIn3DAirspace(point: LatLon, altitudeFeet: number, airspace: AirspacePolygon): boolean {
  if (!isAltitudeInAirspace(altitudeFeet, airspace.minFlightLevel, airspace.maxFlightLevel)) {
    return false;
  }
  return isPointInPolygon(point, airspace.vertices);
}

/**
 * Finds the intersection between line segment (p1 -> p2) and polygon segment (v1 -> v2).
 * Returns fraction along p1->p2 (0..1) if they intersect, or null.
 */
function lineSegmentIntersection(p1: LatLon, p2: LatLon, v1: LatLon, v2: LatLon): number | null {
  const x1 = p1.longitude;
  const y1 = p1.latitude;
  const x2 = p2.longitude;
  const y2 = p2.latitude;

  const x3 = v1.longitude;
  const y3 = v1.latitude;
  const x4 = v2.longitude;
  const y4 = v2.latitude;

  const denom = (y4 - y3) * (x2 - x1) - (x4 - x3) * (y2 - y1);
  if (Math.abs(denom) < 1e-12) return null; // parallel or collinear

  const ua = ((x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)) / denom;
  const ub = ((x1 - x3) * (y2 - y1) - (y1 - y3) * (x2 - x1)) / denom;

  if (ua >= 0 && ua <= 1 && ub >= 0 && ub <= 1) {
    return ua;
  }

  return null;
}

/**
 * Detects crossings of an airspace polygon by a segment from p1 to p2.
 */
export function findAirspaceCrossings(
  p1: LatLon,
  p2: LatLon,
  startAltFeet: number,
  endAltFeet: number,
  airspace: AirspacePolygon,
  legStartDistFromFlightStartNm: number
): FirCrossing[] {
  const crossings: FirCrossing[] = [];
  const legDistance = calculateDistanceNm(p1, p2);
  const verts = airspace.vertices;

  for (let i = 0; i < verts.length; i++) {
    const v1 = verts[i];
    const v2 = verts[(i + 1) % verts.length];
    const frac = lineSegmentIntersection(p1, p2, v1, v2);

    if (frac !== null && frac >= 0 && frac <= 1.0) {
      const crossingPoint = interpolateIntermediatePoint(p1, p2, frac);
      const altAtCrossing = startAltFeet + (endAltFeet - startAltFeet) * frac;
      const fl = Math.round(altAtCrossing / 100);

      // Check if vertical altitude at crossing is within airspace FL bounds
      if (isAltitudeInAirspace(altAtCrossing, airspace.minFlightLevel, airspace.maxFlightLevel)) {
        crossings.push({
          airspaceId: airspace.airspaceId,
          entryPoint: crossingPoint,
          entryFraction: frac,
          distanceFromStartNm: legStartDistFromFlightStartNm + legDistance * frac,
          flightLevel: fl
        });
      }
    }
  }

  return crossings.sort((a, b) => a.entryFraction - b.entryFraction);
}
