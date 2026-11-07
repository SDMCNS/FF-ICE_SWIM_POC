/**
 * Validation Engine for FF-ICE Flight Plans (ICAO Doc 9965 & FIXM)
 */
import { FficeFlightPlan } from './types.js';
import { isValidGufi } from './gufi.js';

export interface ValidationIssue {
  field: string;
  message: string;
  severity: 'ERROR' | 'WARNING';
}

export interface ValidationReport {
  isValid: boolean;
  issues: ValidationIssue[];
}

export function validateFficeFlightPlan(plan: FficeFlightPlan): ValidationReport {
  const issues: ValidationIssue[] = [];

  // 1. GUFI validation
  if (!plan.gufi) {
    issues.push({ field: 'gufi', message: 'GUFI is required for all FF-ICE messages.', severity: 'ERROR' });
  } else if (!isValidGufi(plan.gufi)) {
    issues.push({ field: 'gufi', message: `GUFI "${plan.gufi}" is not a valid RFC 4122 UUID.`, severity: 'ERROR' });
  }

  // 2. Flight Identification
  if (!plan.flightIdentification?.aircraftIdentification || plan.flightIdentification.aircraftIdentification.trim() === '') {
    issues.push({ field: 'flightIdentification.aircraftIdentification', message: 'Aircraft callsign is required.', severity: 'ERROR' });
  }

  // 3. Departure & Arrival Aerodromes
  const dep = plan.departure?.aerodrome?.trim().toUpperCase();
  const arr = plan.arrival?.aerodrome?.trim().toUpperCase();

  if (!dep || dep.length !== 4) {
    issues.push({ field: 'departure.aerodrome', message: 'Departure aerodrome must be a 4-letter ICAO indicator.', severity: 'ERROR' });
  }

  if (!arr || arr.length !== 4) {
    issues.push({ field: 'arrival.aerodrome', message: 'Arrival aerodrome must be a 4-letter ICAO indicator.', severity: 'ERROR' });
  }

  if (dep && arr && dep === arr) {
    issues.push({ field: 'arrival.aerodrome', message: 'Departure and arrival aerodromes cannot be identical.', severity: 'ERROR' });
  }

  // 4. Time consistency
  const eobt = Date.parse(plan.departure?.estimatedOffBlockTime);
  const eta = Date.parse(plan.arrival?.estimatedTimeOfArrival);

  if (isNaN(eobt)) {
    issues.push({ field: 'departure.estimatedOffBlockTime', message: 'Invalid or missing Estimated Off-Block Time (EOBT).', severity: 'ERROR' });
  }

  if (isNaN(eta)) {
    issues.push({ field: 'arrival.estimatedTimeOfArrival', message: 'Invalid or missing Estimated Time of Arrival (ETA).', severity: 'ERROR' });
  }

  if (!isNaN(eobt) && !isNaN(eta) && eta <= eobt) {
    issues.push({ field: 'arrival.estimatedTimeOfArrival', message: 'Estimated Time of Arrival (ETA) must be after EOBT.', severity: 'ERROR' });
  }

  // 5. 4D Trajectory checks
  const points = plan.trajectory?.points4D;
  if (!points || points.length < 2) {
    issues.push({ field: 'trajectory.points4D', message: 'Trajectory must contain at least departure and arrival points.', severity: 'ERROR' });
  } else {
    // Check monotonic distance & time progression
    for (let i = 1; i < points.length; i++) {
      if (points[i].cumulativeDistanceNm < points[i - 1].cumulativeDistanceNm) {
        issues.push({
          field: `trajectory.points4D[${i}]`,
          message: `Trajectory point "${points[i].identifier}" distance (${points[i].cumulativeDistanceNm} NM) is less than preceding point (${points[i - 1].cumulativeDistanceNm} NM).`,
          severity: 'ERROR'
        });
      }
      if (points[i].cumulativeTimeSeconds < points[i - 1].cumulativeTimeSeconds) {
        issues.push({
          field: `trajectory.points4D[${i}]`,
          message: `Trajectory point "${points[i].identifier}" elapsed time (${points[i].cumulativeTimeSeconds} s) is earlier than preceding point (${points[i - 1].cumulativeTimeSeconds} s).`,
          severity: 'ERROR'
        });
      }
    }
  }

  return {
    isValid: !issues.some(i => i.severity === 'ERROR'),
    issues
  };
}

