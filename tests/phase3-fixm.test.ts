import { AeroStore } from '../src/data/aero-store.js';
import { getAircraftPerformance } from '../src/performance/aircraft-database.js';
import { calculate4DTrajectory } from '../src/performance/trajectory-calculator.js';
import { generateGufi, formatGufiUrn } from '../src/ffice/gufi.js';
import { serializeToFixmXml, serializeToFixmJson } from '../src/ffice/fixm-serializer.js';
import { parseFixmXml, parseFixmJson } from '../src/ffice/fixm-deserializer.js';
import { validateFficeFlightPlan } from '../src/ffice/validator.js';
import { FficeFlightPlan } from '../src/ffice/types.js';

async function testPhase3() {
  console.log('--- Phase 3: FIXM Serialization, Deserialization & Validation Tests ---');

  const store = new AeroStore();
  await store.initialize();

  const egll = store.getAirport('EGLL')!;
  const eidw = store.getAirport('EIDW')!;
  const a320 = getAircraftPerformance('A320');
  const lipgo = store.getWaypoint('LIPGO');
  const waypoints = lipgo ? [lipgo] : [];

  const eobt = '2026-11-07T14:30:00.000Z';
  const trajectory = calculate4DTrajectory({
    departure: egll,
    destination: eidw,
    waypoints,
    aircraft: a320,
    requestedCruiseFl: 280,
    estimatedOffBlockTime: eobt
  }, store.getAllFirs());

  const gufi = generateGufi();
  console.log(`[PASS] Generated GUFI: ${gufi} (${formatGufiUrn(gufi)})`);

  const flightPlan: FficeFlightPlan = {
    gufi,
    status: 'FILED',
    messageType: 'FILING',
    filingTime: new Date().toISOString(),
    flightIdentification: {
      aircraftIdentification: 'EIN157',
      aircraftRegistration: 'EI-DVM'
    },
    aircraft: {
      aircraftType: a320.icaoType,
      wakeTurbulence: a320.wakeTurbulenceCategory,
      capabilities: {
        standardEquipment: a320.defaultEquipment,
        navigation: ['RNAV 1', 'RNAV 5', 'RNP 4'],
        communication: ['VHF 8.33 kHz', 'CPDLC'],
        surveillance: ['ADS-B Out', 'Mode S Transponder']
      }
    },
    departure: {
      aerodrome: egll.icao,
      runway: '27R',
      elevationFeet: egll.elevationFeet,
      estimatedOffBlockTime: eobt
    },
    arrival: {
      aerodrome: eidw.icao,
      runway: '28L',
      elevationFeet: eidw.elevationFeet,
      estimatedTimeOfArrival: trajectory.points[trajectory.points.length - 1].estimatedTimestamp
    },
    enRoute: {
      cruisingLevel: 'F280',
      cruisingSpeed: 'N0450',
      routeString: `EGLL ${waypoints.map(w => w.name).join(' ')} EIDW`,
      airspaceCrossings: trajectory.firCrossings
    },
    trajectory: {
      points4D: trajectory.points,
      topOfClimb: trajectory.topOfClimb,
      topOfDescent: trajectory.topOfDescent,
      totalDistanceNm: trajectory.totalDistanceNm,
      totalFlightTimeMinutes: trajectory.totalFlightTimeMinutes
    },
    remarks: 'SPEED BIRD OPR / FF-ICE TRIAL / SWIM COMPLIANT'
  };

  // Test 1: Validation
  const valResult = validateFficeFlightPlan(flightPlan);
  console.log(`[PASS] Validation result: isValid=${valResult.isValid}, issues=${valResult.issues.length}`);
  if (!valResult.isValid) {
    throw new Error(`Validation failed: ${JSON.stringify(valResult.issues)}`);
  }

  // Test 2: FIXM XML Serialization
  const fixmXml = serializeToFixmXml(flightPlan);
  console.log(`[PASS] Serialized FIXM XML length: ${fixmXml.length} chars`);
  if (!fixmXml.includes('<fx:Flight') || !fixmXml.includes(gufi)) {
    throw new Error('FIXM XML does not contain expected Flight or GUFI tags');
  }

  // Test 3: FIXM XML Deserialization round-trip
  const parsedFromXml = parseFixmXml(fixmXml);
  console.log(`[PASS] Deserialized from XML:`);
  console.log(`       GUFI: ${parsedFromXml.gufi}`);
  console.log(`       Callsign: ${parsedFromXml.flightIdentification.aircraftIdentification}`);
  console.log(`       Departure: ${parsedFromXml.departure.aerodrome} (Elev: ${parsedFromXml.departure.elevationFeet} ft)`);
  console.log(`       Arrival: ${parsedFromXml.arrival.aerodrome} (Elev: ${parsedFromXml.arrival.elevationFeet} ft)`);
  console.log(`       Trajectory points restored: ${parsedFromXml.trajectory.points4D.length}`);

  if (parsedFromXml.gufi !== flightPlan.gufi) {
    throw new Error(`Round-trip GUFI mismatch: expected ${flightPlan.gufi}, got ${parsedFromXml.gufi}`);
  }

  if (parsedFromXml.trajectory.points4D.length !== flightPlan.trajectory.points4D.length) {
    throw new Error(`Round-trip points count mismatch: expected ${flightPlan.trajectory.points4D.length}, got ${parsedFromXml.trajectory.points4D.length}`);
  }

  // Test 4: FIXM JSON Serialization & Deserialization
  const fixmJson = serializeToFixmJson(flightPlan);
  const parsedFromJson = parseFixmJson(fixmJson);
  console.log(`[PASS] Serialized and restored FIXM JSON successfully (GUFI: ${parsedFromJson.gufi})`);

  console.log('\n>>> ALL PHASE 3 TESTS PASSED SUCCESSFULLY! <<<\n');
}

testPhase3().catch(e => {
  console.error('Phase 3 test failed:', e);
  process.exit(1);
});

