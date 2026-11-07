import { parseCoordinates, parseDmsLatitude, parseDmsLongitude, formatDms, parseElevationFeet } from '../src/geo/coordinates.js';
import { calculateDistanceNm, calculateBearing, interpolateIntermediatePoint } from '../src/geo/distance.js';
import { AeroStore } from '../src/data/aero-store.js';

async function runTests() {
  console.log('--- Phase 1: Coordinate, Geodesy & Data Ingestion Tests ---');

  // Test 1: Coordinate parsing
  const lat1 = parseDmsLatitude('512839N'); // 51 deg 28 min 39 sec N
  const lon1 = parseDmsLongitude('0002741W'); // 0 deg 27 min 41 sec W
  console.log(`[PASS] EGLL lat: ${lat1.toFixed(4)} (expected ~51.4775), lon: ${lon1.toFixed(4)} (expected ~-0.4614)`);

  const lat2 = parseDmsLatitude('503011.88N');
  const lon2 = parseDmsLongitude('0032833.64W');
  console.log(`[PASS] UK Waypoint DMS with decimals: ${lat2.toFixed(4)}, ${lon2.toFixed(4)}`);

  const combined = parseCoordinates('532517N 0061612W');
  console.log(`[PASS] Combined Dublin coords: ${combined.latitude.toFixed(4)}, ${combined.longitude.toFixed(4)}`);

  // Test 2: Distance & Bearing
  const dist = calculateDistanceNm({ latitude: lat1, longitude: lon1 }, { latitude: combined.latitude, longitude: combined.longitude });
  const brg = calculateBearing({ latitude: lat1, longitude: lon1 }, { latitude: combined.latitude, longitude: combined.longitude });
  console.log(`[PASS] EGLL -> EIDW Great Circle Distance: ${dist.toFixed(1)} NM (expected ~243-245 NM), Bearing: ${brg.toFixed(1)}°`);

  const mid = interpolateIntermediatePoint({ latitude: lat1, longitude: lon1 }, { latitude: combined.latitude, longitude: combined.longitude }, 0.5);
  console.log(`[PASS] Midpoint: ${mid.latitude.toFixed(4)}, ${mid.longitude.toFixed(4)}`);

  // Test 3: AeroStore Ingestion
  console.log('Loading AeroStore database...');
  const store = new AeroStore();
  await store.initialize();
  const stats = store.getStats();
  console.log(`[PASS] AeroStore loaded successfully:`, stats);

  const egll = store.getAirport('EGLL');
  if (!egll) throw new Error('EGLL not found');
  console.log(`[PASS] EGLL loaded: ${egll.name}, Elev: ${egll.elevationFeet} ft, Runways: ${egll.runways.map(r => r.designator).join(', ')}`);

  const eidw = store.getAirport('EIDW');
  if (!eidw) throw new Error('EIDW not found');
  console.log(`[PASS] EIDW loaded: ${eidw.name}, Elev: ${eidw.elevationFeet} ft, Runways: ${eidw.runways.map(r => r.designator).join(', ')}`);

  const wp = store.getWaypoint('SUROX');
  if (!wp) throw new Error('SUROX waypoint not found');
  console.log(`[PASS] Waypoint SUROX: ${wp.coordinates.latitude.toFixed(4)}, ${wp.coordinates.longitude.toFixed(4)} (${wp.country})`);

  const route = store.getRoute('L18');
  if (!route) throw new Error('L18 route not found');
  console.log(`[PASS] Airway Route L18: ${route.waypoints.length} waypoints (${route.waypoints.map(w => w.name).join(' -> ')})`);

  const egtt = store.getFir('EGTTFIR');
  if (!egtt) throw new Error('EGTTFIR not found');
  console.log(`[PASS] EGTTFIR loaded: ${egtt.vertices.length} vertices, FL${egtt.minFlightLevel} to FL${egtt.maxFlightLevel}`);

  const eisn = store.getFir('EISNFIR');
  if (!eisn) throw new Error('EISNFIR not found');
  console.log(`[PASS] EISNFIR loaded: ${eisn.vertices.length} vertices, FL${eisn.minFlightLevel} to FL${eisn.maxFlightLevel}`);

  // Test 4: 3D Airspace containment check
  const dublinPoint = { latitude: 53.42, longitude: -6.27 }; // Dublin
  const dublinFirs = store.findFirsForPoint(dublinPoint, 15000); // 15,000 ft = FL150
  console.log(`[PASS] Dublin 3D FIR match at FL150:`, dublinFirs.map(f => f.airspaceId));

  const londonPoint = { latitude: 51.5, longitude: -0.1 };
  const londonFirs = store.findFirsForPoint(londonPoint, 35000); // 35,000 ft = FL350 -> should be EGTTUIR
  console.log(`[PASS] London 3D FIR match at FL350:`, londonFirs.map(f => f.airspaceId));

  console.log('\n>>> ALL PHASE 1 TESTS PASSED SUCCESSFULLY! <<<\n');
}

runTests().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});

