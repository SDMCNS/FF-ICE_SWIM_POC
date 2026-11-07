/**
 * Flight Plan Altitude & Route Sanity Checker
 */
import { AircraftPerformance } from './aircraft-database.js';
import { LatLon } from '../geo/coordinates.js';
import { calculateDistanceNm, calculateBearing } from '../geo/distance.js';

export interface SanityCheckResult {
  isValid: boolean;
  warnings: string[];
  errors: string[];
  recommendedCruiseFl?: number;
  climbDistanceNm: number;
  descentDistanceNm: number;
  minimumRequiredDistanceNm: number;
  totalRouteDistanceNm: number;
  semicircularExpected: 'ODD' | 'EVEN';
  semicircularCompliant: boolean;
}

export function checkFlightPlanSanity(
  depElevFt: number,
  destElevFt: number,
  totalRouteDistanceNm: number,
  requestedCruiseFl: number,
  aircraft: AircraftPerformance,
  initialBearingDeg: number
): SanityCheckResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  const cruiseAltFt = requestedCruiseFl * 100;

  // 1. Service ceiling check
  if (requestedCruiseFl > aircraft.serviceCeilingFl) {
    errors.push(
      `Requested cruise level FL${requestedCruiseFl} exceeds aircraft service ceiling FL${aircraft.serviceCeilingFl} (${aircraft.manufacturer} ${aircraft.model}).`
    );
  }

  // 2. Climb & Descent distance calculation
  const climbAltGain = Math.max(0, cruiseAltFt - depElevFt);
  const climbMinutes = climbAltGain / aircraft.averageClimbRateFpm;
  const climbDistanceNm = (climbMinutes / 60) * aircraft.averageClimbSpeedKnots;

  const descentAltLoss = Math.max(0, cruiseAltFt - destElevFt);
  const descentDistanceNm = descentAltLoss / aircraft.descentGradientFtPerNm;

  const minCruiseBufferNm = 15; // At least 15 NM in level cruise
  const minRequiredDistanceNm = climbDistanceNm + descentDistanceNm + minCruiseBufferNm;

  let recommendedCruiseFl = requestedCruiseFl;

  // 3. Distance Feasibility Check
  if (minRequiredDistanceNm > totalRouteDistanceNm) {
    warnings.push(
      `Route distance (${totalRouteDistanceNm.toFixed(1)} NM) is too short to reach FL${requestedCruiseFl}. Climb and descent require at least ${minRequiredDistanceNm.toFixed(1)} NM.`
    );

    // Calculate maximum achievable flight level
    // Solve: (h - depElev) * (climbSpeed / (60 * climbRate)) + (h - destElev) / descentGradient = totalDist - minCruiseBuffer
    const targetDist = Math.max(20, totalRouteDistanceNm - minCruiseBufferNm);
    const climbFactor = aircraft.averageClimbSpeedKnots / (60 * aircraft.averageClimbRateFpm);
    const descentFactor = 1 / aircraft.descentGradientFtPerNm;

    const maxAchievableFt = (targetDist + depElevFt * climbFactor + destElevFt * descentFactor) / (climbFactor + descentFactor);
    let maxFl = Math.floor(maxAchievableFt / 1000) * 10;
    maxFl = Math.min(maxFl, aircraft.serviceCeilingFl);
    maxFl = Math.max(maxFl, 40); // minimum practical FL40

    recommendedCruiseFl = maxFl;
  }

  // 4. ICAO Semicircular Rule Check (Eastbound ODD, Westbound EVEN)
  const normBearing = (initialBearingDeg % 360 + 360) % 360;
  const semicircularExpected: 'ODD' | 'EVEN' = (normBearing >= 0 && normBearing < 180) ? 'ODD' : 'EVEN';

  const isFlOdd = Math.floor(requestedCruiseFl / 10) % 2 === 1;
  const semicircularCompliant = (semicircularExpected === 'ODD' && isFlOdd) ||
                                (semicircularExpected === 'EVEN' && !isFlOdd);

  if (!semicircularCompliant && requestedCruiseFl >= 30) {
    warnings.push(
      `FL${requestedCruiseFl} does not comply with the standard semicircular rule for track ${normBearing.toFixed(0)}° (expected ${semicircularExpected} flight level).`
    );

    // Adjust recommended FL to match semicircular rule
    const recIsOdd = Math.floor(recommendedCruiseFl / 10) % 2 === 1;
    if (semicircularExpected === 'ODD' && !recIsOdd) {
      recommendedCruiseFl = Math.max(30, recommendedCruiseFl - 10);
    } else if (semicircularExpected === 'EVEN' && recIsOdd) {
      recommendedCruiseFl = Math.max(40, recommendedCruiseFl - 10);
    }
  }

  return {
    isValid: errors.length === 0,
    warnings,
    errors,
    recommendedCruiseFl,
    climbDistanceNm,
    descentDistanceNm,
    minimumRequiredDistanceNm: minRequiredDistanceNm,
    totalRouteDistanceNm,
    semicircularExpected,
    semicircularCompliant
  };
}
