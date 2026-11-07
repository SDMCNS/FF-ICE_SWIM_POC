/**
 * 4D Trajectory Calculator with Climb, Cruise, Descent, and 3D FIR Airspace Crossings
 */
import { LatLon } from '../geo/coordinates.js';
import { calculateDistanceNm, calculateBearing, interpolateIntermediatePoint } from '../geo/distance.js';
import { AirspacePolygon, findAirspaceCrossings, isPointIn3DAirspace } from '../geo/fir-spatial.js';
import { AircraftPerformance } from './aircraft-database.js';
import { Airport, Waypoint, FirAirspace } from '../data/types.js';
import { checkFlightPlanSanity, SanityCheckResult } from './sanity-checker.js';

export type PointType = 'DEPARTURE' | 'TOC' | 'WAYPOINT' | 'FIR_CROSSING' | 'TOD' | 'DESTINATION';

export interface TrajectoryPoint4D {
  pointType: PointType;
  identifier: string;
  coordinates: LatLon;
  altitudeFeet: number;
  flightLevel: number;
  cumulativeDistanceNm: number;
  groundSpeedKnots: number;
  cumulativeTimeSeconds: number;
  estimatedTimestamp: string;
  pointSource: string;
  associatedAirspace?: string;
}

export interface FirCrossingSummary {
  exitingAirspace?: string;
  enteringAirspace: string;
  point: LatLon;
  flightLevel: number;
  timestamp: string;
  distanceFromStartNm: number;
}

export interface CalculatedTrajectory {
  points: TrajectoryPoint4D[];
  totalDistanceNm: number;
  totalFlightTimeMinutes: number;
  topOfClimb: TrajectoryPoint4D;
  topOfDescent: TrajectoryPoint4D;
  firCrossings: FirCrossingSummary[];
  sanityResult: SanityCheckResult;
}

export interface TrajectoryCalculationRequest {
  departure: Airport;
  destination: Airport;
  waypoints: Waypoint[];
  aircraft: AircraftPerformance;
  requestedCruiseFl: number;
  estimatedOffBlockTime?: string; // ISO string, defaults to current time
}

export function calculate4DTrajectory(
  req: TrajectoryCalculationRequest,
  firs: FirAirspace[] = []
): CalculatedTrajectory {
  const eobt = req.estimatedOffBlockTime ? new Date(req.estimatedOffBlockTime) : new Date();

  // 1. Build initial route anchor points
  interface RouteAnchor {
    name: string;
    coordinates: LatLon;
    isAirport: boolean;
  }

  const anchors: RouteAnchor[] = [
    { name: req.departure.icao, coordinates: req.departure.coordinates, isAirport: true },
    ...req.waypoints.map(w => ({ name: w.name, coordinates: w.coordinates, isAirport: false })),
    { name: req.destination.icao, coordinates: req.destination.coordinates, isAirport: true }
  ];

  // 2. Measure cumulative distance of all anchors
  const legDistances: number[] = [];
  const cumulativeDistances: number[] = [0];
  let totalDist = 0;

  for (let i = 0; i < anchors.length - 1; i++) {
    const d = calculateDistanceNm(anchors[i].coordinates, anchors[i + 1].coordinates);
    legDistances.push(d);
    totalDist += d;
    cumulativeDistances.push(totalDist);
  }

  const initialBearing = calculateBearing(anchors[0].coordinates, anchors[1].coordinates);

  // 3. Perform sanity check
  const sanityResult = checkFlightPlanSanity(
    req.departure.elevationFeet,
    req.destination.elevationFeet,
    totalDist,
    req.requestedCruiseFl,
    req.aircraft,
    initialBearing
  );

  const effectiveCruiseFl = sanityResult.recommendedCruiseFl ?? req.requestedCruiseFl;
  const cruiseAltFt = effectiveCruiseFl * 100;

  // 4. Compute Top of Climb (TOC) and Top of Descent (TOD) distances
  const climbAltGain = Math.max(0, cruiseAltFt - req.departure.elevationFeet);
  const climbMinutes = climbAltGain / req.aircraft.averageClimbRateFpm;
  const tocDistanceNm = Math.min((climbMinutes / 60) * req.aircraft.averageClimbSpeedKnots, totalDist * 0.48);

  const descentAltLoss = Math.max(0, cruiseAltFt - req.destination.elevationFeet);
  const descentDistanceNm = Math.min(descentAltLoss / req.aircraft.descentGradientFtPerNm, totalDist * 0.48);
  const todDistanceNm = Math.max(tocDistanceNm + 1, totalDist - descentDistanceNm);

  // Helper to find location along the route given distance from start
  function getLocationAtDistance(targetDistNm: number): { coords: LatLon; legIndex: number } {
    if (targetDistNm <= 0) return { coords: anchors[0].coordinates, legIndex: 0 };
    if (targetDistNm >= totalDist) return { coords: anchors[anchors.length - 1].coordinates, legIndex: anchors.length - 2 };

    for (let i = 0; i < anchors.length - 1; i++) {
      const segStart = cumulativeDistances[i];
      const segEnd = cumulativeDistances[i + 1];
      if (targetDistNm >= segStart && targetDistNm <= segEnd) {
        const segLen = segEnd - segStart;
        const frac = segLen > 0 ? (targetDistNm - segStart) / segLen : 0;
        return {
          coords: interpolateIntermediatePoint(anchors[i].coordinates, anchors[i + 1].coordinates, frac),
          legIndex: i
        };
      }
    }
    return { coords: anchors[anchors.length - 1].coordinates, legIndex: anchors.length - 2 };
  }

  // Helper to calculate altitude at distance along route
  function getAltitudeAtDistance(distNm: number): number {
    if (distNm <= 0) return req.departure.elevationFeet;
    if (distNm >= totalDist) return req.destination.elevationFeet;

    if (distNm <= tocDistanceNm) {
      const frac = tocDistanceNm > 0 ? distNm / tocDistanceNm : 1;
      return req.departure.elevationFeet + (cruiseAltFt - req.departure.elevationFeet) * frac;
    } else if (distNm >= todDistanceNm) {
      const frac = (distNm - todDistanceNm) / (totalDist - todDistanceNm);
      return cruiseAltFt - (cruiseAltFt - req.destination.elevationFeet) * frac;
    } else {
      return cruiseAltFt;
    }
  }

  // Helper to calculate ground speed at distance
  function getSpeedAtDistance(distNm: number): number {
    if (distNm < tocDistanceNm) return req.aircraft.averageClimbSpeedKnots;
    if (distNm > todDistanceNm) return req.aircraft.averageDescentSpeedKnots;
    return req.aircraft.cruiseTasKnots;
  }

  // 5. Build raw key sequence (Anchors + TOC + TOD)
  interface KeyStop {
    pointType: PointType;
    name: string;
    distanceNm: number;
    coordinates: LatLon;
    pointSource: string;
  }

  const stops: KeyStop[] = [];

  // Departure
  stops.push({
    pointType: 'DEPARTURE',
    name: req.departure.icao,
    distanceNm: 0,
    coordinates: req.departure.coordinates,
    pointSource: 'DEPARTURE'
  });

  // TOC
  const tocLoc = getLocationAtDistance(tocDistanceNm);
  stops.push({
    pointType: 'TOC',
    name: 'TOC',
    distanceNm: tocDistanceNm,
    coordinates: tocLoc.coords,
    pointSource: 'CALCULATED_CLIMB'
  });

  // Enroute waypoints
  for (let i = 1; i < anchors.length - 1; i++) {
    stops.push({
      pointType: 'WAYPOINT',
      name: anchors[i].name,
      distanceNm: cumulativeDistances[i],
      coordinates: anchors[i].coordinates,
      pointSource: 'PUBLISHED_WAYPOINT'
    });
  }

  // TOD
  const todLoc = getLocationAtDistance(todDistanceNm);
  stops.push({
    pointType: 'TOD',
    name: 'TOD',
    distanceNm: todDistanceNm,
    coordinates: todLoc.coords,
    pointSource: 'CALCULATED_DESCENT'
  });

  // Destination
  stops.push({
    pointType: 'DESTINATION',
    name: req.destination.icao,
    distanceNm: totalDist,
    coordinates: req.destination.coordinates,
    pointSource: 'DESTINATION'
  });

  // Sort stops by distance
  stops.sort((a, b) => a.distanceNm - b.distanceNm);

  // 6. Check for FIR Airspace Crossings between stops
  const firCrossings: FirCrossingSummary[] = [];
  const fullStops: KeyStop[] = [];

  for (let i = 0; i < stops.length - 1; i++) {
    const s1 = stops[i];
    const s2 = stops[i + 1];
    fullStops.push(s1);

    const alt1 = getAltitudeAtDistance(s1.distanceNm);
    const alt2 = getAltitudeAtDistance(s2.distanceNm);

    // Check each FIR boundary
    for (const fir of firs) {
      const airspacePoly: AirspacePolygon = {
        airspaceId: fir.airspaceId,
        minFlightLevel: fir.minFlightLevel,
        maxFlightLevel: fir.maxFlightLevel,
        vertices: fir.vertices
      };

      const crossings = findAirspaceCrossings(
        s1.coordinates,
        s2.coordinates,
        alt1,
        alt2,
        airspacePoly,
        s1.distanceNm
      );

      for (const cross of crossings) {
        fullStops.push({
          pointType: 'FIR_CROSSING',
          name: `${cross.airspaceId}`,
          distanceNm: cross.distanceFromStartNm,
          coordinates: cross.entryPoint,
          pointSource: 'AIRSPACE_BOUNDARY'
        });
      }
    }
  }
  fullStops.push(stops[stops.length - 1]);

  // Remove potential duplicate distances within 0.1 NM and sort
  fullStops.sort((a, b) => a.distanceNm - b.distanceNm);
  const dedupedStops: KeyStop[] = [];
  for (let i = 0; i < fullStops.length; i++) {
    if (i === 0 || Math.abs(fullStops[i].distanceNm - fullStops[i - 1].distanceNm) > 0.05) {
      dedupedStops.push(fullStops[i]);
    }
  }

  // 7. Calculate time, ground speed, and timestamps for all 4D points
  let cumTimeSec = 0;
  const points4D: TrajectoryPoint4D[] = [];

  for (let i = 0; i < dedupedStops.length; i++) {
    const curr = dedupedStops[i];
    const alt = getAltitudeAtDistance(curr.distanceNm);
    const speed = getSpeedAtDistance(curr.distanceNm);

    if (i > 0) {
      const prev = dedupedStops[i - 1];
      const dDist = curr.distanceNm - prev.distanceNm;
      const avgSpeed = (speed + points4D[i - 1].groundSpeedKnots) / 2;
      const legSec = avgSpeed > 0 ? (dDist / avgSpeed) * 3600 : 0;
      cumTimeSec += legSec;
    }

    const pointTime = new Date(eobt.getTime() + cumTimeSec * 1000);
    const fl = Math.round(alt / 100);

    // Identify current FIR
    let matchingAirspace = firs.find(f => isPointIn3DAirspace(curr.coordinates, alt, f))?.airspaceId;

    const pt: TrajectoryPoint4D = {
      pointType: curr.pointType,
      identifier: curr.name,
      coordinates: curr.coordinates,
      altitudeFeet: Math.round(alt),
      flightLevel: fl,
      cumulativeDistanceNm: Number(curr.distanceNm.toFixed(2)),
      groundSpeedKnots: Math.round(speed),
      cumulativeTimeSeconds: Math.round(cumTimeSec),
      estimatedTimestamp: pointTime.toISOString(),
      pointSource: curr.pointSource,
      associatedAirspace: matchingAirspace
    };

    points4D.push(pt);

    if (curr.pointType === 'FIR_CROSSING') {
      firCrossings.push({
        enteringAirspace: curr.name,
        point: curr.coordinates,
        flightLevel: fl,
        timestamp: pointTime.toISOString(),
        distanceFromStartNm: Number(curr.distanceNm.toFixed(2))
      });
    }
  }

  const tocPoint = points4D.find(p => p.pointType === 'TOC') || points4D[0];
  const todPoint = points4D.find(p => p.pointType === 'TOD') || points4D[points4D.length - 1];

  return {
    points: points4D,
    totalDistanceNm: Number(totalDist.toFixed(1)),
    totalFlightTimeMinutes: Number((cumTimeSec / 60).toFixed(1)),
    topOfClimb: tocPoint,
    topOfDescent: todPoint,
    firCrossings,
    sanityResult
  };
}

