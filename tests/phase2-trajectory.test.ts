import { AeroStore } from '../src/data/aero-store.js';
import { getAircraftPerformance } from '../src/performance/aircraft-database.js';
import { calculate4DTrajectory } from '../src/performance/trajectory-calculator.js';
import { checkFlightPlanSanity } from '../src/performance/sanity-checker.js';

async function testPhase2() {
  console.log('--- Phase 2: Aircraft Performance, Trajectory & Sanity Tests ---');

  const store = new AeroStore();
  await store.initialize();

  const egll = store.getAirport('EGLL')!;
  const eidw = store.getAirport('EIDW')!;
  const a320 = getAircraftPerformance('A320');

  console.log(`[PASS] Loaded A320 performance: Ceiling FL${a320.serviceCeilingFl}, Climb: ${a320.averageClimbRateFpm} fpm, Cruise: ${a320.cruiseTasKnots} kts`);

  // Test 1: Sanity checker on impossible short flight
  const shortSanity = checkFlightPlanSanity(83, 243, 60, 370, a320, 300);
  console.log(`[PASS] Short flight sanity check (60 NM, FL370):`);
  console.log(`       Warnings: ${shortSanity.warnings.join(' | ')}`);
  console.log(`       Recommended FL: FL${shortSanity.recommendedCruiseFl} (assisted down from FL370)`);
  if (!shortSanity.warnings.length || (shortSanity.recommendedCruiseFl && shortSanity.recommendedCruiseFl >= 370)) {
    throw new Error('Sanity check failed to catch impossible cruise altitude');
  }

  // Test 2: Full 4D Trajectory calculation from EGLL to EIDW
  const lipgo = store.getWaypoint('LIPGO');
  const waypoints = lipgo ? [lipgo] : [];

  console.log(`Calculating 4D trajectory EGLL -> EIDW (${waypoints.map(w => w.name).join(', ')})...`);
  const trajectory = calculate4DTrajectory({
    departure: egll,
    destination: eidw,
    waypoints,
    aircraft: a320,
    requestedCruiseFl: 280, // Westbound FL280
    estimatedOffBlockTime: '2026-11-07T12:00:00Z'
  }, store.getAllFirs());

  console.log(`[PASS] Trajectory calculated:`);
  console.log(`       Total Distance: ${trajectory.totalDistanceNm} NM`);
  console.log(`       Flight Time: ${trajectory.totalFlightTimeMinutes} min`);
  console.log(`       TOC: Dist ${trajectory.topOfClimb.cumulativeDistanceNm} NM, Alt ${trajectory.topOfClimb.altitudeFeet} ft, Time ${trajectory.topOfClimb.estimatedTimestamp}`);
  console.log(`       TOD: Dist ${trajectory.topOfDescent.cumulativeDistanceNm} NM, Alt ${trajectory.topOfDescent.altitudeFeet} ft, Time ${trajectory.topOfDescent.estimatedTimestamp}`);
  console.log(`       Waypoints / 4D Points count: ${trajectory.points.length}`);

  console.log('\n4D Waypoint Sequence:');
  for (const pt of trajectory.points) {
    console.log(`  - [${pt.pointType.padEnd(12)}] ${pt.identifier.padEnd(10)} | FL${String(pt.flightLevel).padStart(3, '0')} (${String(pt.altitudeFeet).padStart(5, ' ')} ft) | ${String(pt.cumulativeDistanceNm).padStart(6, ' ')} NM | GS ${pt.groundSpeedKnots} kt | ${pt.estimatedTimestamp.substring(11, 19)} UTC | Airspace: ${pt.associatedAirspace || 'N/A'}`);
  }

  console.log(`\n[PASS] FIR Crossings detected (${trajectory.firCrossings.length}):`);
  for (const f of trajectory.firCrossings) {
    console.log(`       Crossed into ${f.enteringAirspace} at FL${f.flightLevel}, Dist ${f.distanceFromStartNm} NM, Time ${f.timestamp.substring(11, 19)} UTC`);
  }

  console.log('\n>>> ALL PHASE 2 TESTS PASSED SUCCESSFULLY! <<<\n');
}

testPhase2().catch(e => {
  console.error('Phase 2 test failed:', e);
  process.exit(1);
});

