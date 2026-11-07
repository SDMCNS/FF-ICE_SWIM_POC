/**
 * Geodesy, Distance, and Bearing Utilities for Aviation Navigation (WGS84 spherical approximation)
 */
import { LatLon } from './coordinates.js';

const EARTH_RADIUS_NM = 3440.065; // Earth radius in Nautical Miles
const EARTH_RADIUS_KM = 6371.0;

function toRadians(degrees: number): number {
  return degrees * (Math.PI / 180);
}

function toDegrees(radians: number): number {
  return radians * (180 / Math.PI);
}

/**
 * Calculates Great-Circle distance between two points in Nautical Miles (NM).
 */
export function calculateDistanceNm(p1: LatLon, p2: LatLon): number {
  const phi1 = toRadians(p1.latitude);
  const phi2 = toRadians(p2.latitude);
  const deltaPhi = toRadians(p2.latitude - p1.latitude);
  const deltaLambda = toRadians(p2.longitude - p1.longitude);

  const a = Math.sin(deltaPhi / 2) * Math.sin(deltaPhi / 2) +
            Math.cos(phi1) * Math.cos(phi2) *
            Math.sin(deltaLambda / 2) * Math.sin(deltaLambda / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  return EARTH_RADIUS_NM * c;
}

/**
 * Calculates the initial true bearing (forward azimuth) from p1 to p2 in degrees [0, 360).
 */
export function calculateBearing(p1: LatLon, p2: LatLon): number {
  const phi1 = toRadians(p1.latitude);
  const phi2 = toRadians(p2.latitude);
  const deltaLambda = toRadians(p2.longitude - p1.longitude);

  const y = Math.sin(deltaLambda) * Math.cos(phi2);
  const x = Math.cos(phi1) * Math.sin(phi2) -
            Math.sin(phi1) * Math.cos(phi2) * Math.cos(deltaLambda);

  const theta = Math.atan2(y, x);
  return (toDegrees(theta) + 360) % 360;
}

/**
 * Interpolates an intermediate point along a Great Circle path between p1 and p2.
 * fraction: 0.0 at p1, 1.0 at p2
 */
export function interpolateIntermediatePoint(p1: LatLon, p2: LatLon, fraction: number): LatLon {
  if (fraction <= 0) return { ...p1 };
  if (fraction >= 1) return { ...p2 };

  const phi1 = toRadians(p1.latitude);
  const lambda1 = toRadians(p1.longitude);
  const phi2 = toRadians(p2.latitude);
  const lambda2 = toRadians(p2.longitude);

  const delta = calculateDistanceNm(p1, p2) / EARTH_RADIUS_NM;
  if (delta === 0) return { ...p1 };

  const a = Math.sin((1 - fraction) * delta) / Math.sin(delta);
  const b = Math.sin(fraction * delta) / Math.sin(delta);

  const x = a * Math.cos(phi1) * Math.cos(lambda1) + b * Math.cos(phi2) * Math.cos(lambda2);
  const y = a * Math.cos(phi1) * Math.sin(lambda1) + b * Math.cos(phi2) * Math.sin(lambda2);
  const z = a * Math.sin(phi1) + b * Math.sin(phi2);

  const phi = Math.atan2(z, Math.sqrt(x * x + y * y));
  const lambda = Math.atan2(y, x);

  return {
    latitude: toDegrees(phi),
    longitude: toDegrees(lambda)
  };
}

/**
 * Calculates destination point given starting point, bearing (degrees), and distance (NM).
 */
export function calculateDestinationPoint(start: LatLon, bearingDeg: number, distanceNm: number): LatLon {
  const delta = distanceNm / EARTH_RADIUS_NM;
  const theta = toRadians(bearingDeg);
  const phi1 = toRadians(start.latitude);
  const lambda1 = toRadians(start.longitude);

  const sinPhi2 = Math.sin(phi1) * Math.cos(delta) + Math.cos(phi1) * Math.sin(delta) * Math.cos(theta);
  const phi2 = Math.asin(sinPhi2);
  const y = Math.sin(theta) * Math.sin(delta) * Math.cos(phi1);
  const x = Math.cos(delta) - Math.sin(phi1) * sinPhi2;
  const lambda2 = lambda1 + Math.atan2(y, x);

  return {
    latitude: toDegrees(phi2),
    longitude: ((toDegrees(lambda2) + 540) % 360) - 180
  };
}

