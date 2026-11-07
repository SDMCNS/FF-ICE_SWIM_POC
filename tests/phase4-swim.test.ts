import http from 'http';
import { AeroStore } from '../src/data/aero-store.js';
import { SwimFlightPlanService } from '../src/swim/swim-service.js';
import { createSwimServer } from '../src/swim/server.js';
import { serializeToFixmXml } from '../src/ffice/fixm-serializer.js';

async function testPhase4() {
  console.log('--- Phase 4: SWIM REST API & Service Layer Tests ---');

  const store = new AeroStore();
  const service = new SwimFlightPlanService(store);
  await service.initialize();

  const server = createSwimServer(service);
  const TEST_PORT = 3199;

  await new Promise<void>((resolve) => server.listen(TEST_PORT, resolve));
  console.log(`[PASS] Test SWIM Server listening on port ${TEST_PORT}`);

  try {
    // 1. Test OpenAPI JSON endpoint
    const openapiRes = await fetchJson(`http://localhost:${TEST_PORT}/api/openapi.json`);
    console.log(`[PASS] GET /api/openapi.json: "${openapiRes.info.title}" (v${openapiRes.info.version})`);

    // 2. Test Airport Search
    const airportsRes = await fetchJson(`http://localhost:${TEST_PORT}/api/v1/airports?query=Dublin`);
    console.log(`[PASS] GET /api/v1/airports?query=Dublin: Found ${airportsRes.length} airports (${airportsRes[0]?.icao})`);

    // 3. Test Waypoint Search
    const wpRes = await fetchJson(`http://localhost:${TEST_PORT}/api/v1/waypoints?query=LIP`);
    console.log(`[PASS] GET /api/v1/waypoints?query=LIP: Found ${wpRes.length} waypoints (${wpRes.map((w: any) => w.name).join(', ')})`);

    // 4. Test 4D Trajectory Calculation Endpoint
    const calcBody = {
      departureIcao: 'EGLL',
      arrivalIcao: 'EIDW',
      aircraftType: 'A320',
      requestedCruiseFl: 280,
      waypointNames: ['LIPGO'],
      estimatedOffBlockTime: '2026-11-07T15:00:00Z'
    };
    const trajRes = await postJson(`http://localhost:${TEST_PORT}/api/v1/trajectory/calculate`, calcBody);
    console.log(`[PASS] POST /api/v1/trajectory/calculate:`);
    console.log(`       Dist: ${trajRes.calculated.totalDistanceNm} NM, Flight Time: ${trajRes.calculated.totalFlightTimeMinutes} min, Points: ${trajRes.calculated.points.length}`);

    // 5. Test File Flight Plan (JSON)
    const newPlanPayload = {
      flightIdentification: { aircraftIdentification: 'EIN159' },
      aircraft: {
        aircraftType: 'A320',
        wakeTurbulence: 'M',
        capabilities: {
          standardEquipment: 'SDFGIRW/LB1',
          navigation: ['RNAV 1'],
          communication: ['VHF 8.33 kHz'],
          surveillance: ['Mode S']
        }
      },
      departure: {
        aerodrome: 'EGLL',
        runway: '27R',
        elevationFeet: 83,
        estimatedOffBlockTime: '2026-11-07T15:00:00Z'
      },
      arrival: {
        aerodrome: 'EIDW',
        runway: '28L',
        elevationFeet: 243,
        estimatedTimeOfArrival: '2026-11-07T15:38:00Z'
      },
      enRoute: {
        cruisingLevel: 'F280',
        cruisingSpeed: 'N0450',
        routeString: 'EGLL LIPGO EIDW',
        airspaceCrossings: trajRes.calculated.firCrossings
      },
      trajectory: {
        points4D: trajRes.calculated.points,
        topOfClimb: trajRes.calculated.topOfClimb,
        topOfDescent: trajRes.calculated.topOfDescent,
        totalDistanceNm: trajRes.calculated.totalDistanceNm,
        totalFlightTimeMinutes: trajRes.calculated.totalFlightTimeMinutes
      }
    };

    const fileRes = await postJson(`http://localhost:${TEST_PORT}/api/v1/ffice/plans`, newPlanPayload);
    const filedGufi = fileRes.plan.gufi;
    console.log(`[PASS] POST /api/v1/ffice/plans: Plan filed with GUFI ${filedGufi}`);

    // 6. Test Retrieve Flight Plan by GUFI (JSON)
    const getRes = await fetchJson(`http://localhost:${TEST_PORT}/api/v1/ffice/plans/${filedGufi}`);
    console.log(`[PASS] GET /api/v1/ffice/plans/${filedGufi}: Status=${getRes.status}, Callsign=${getRes.flightIdentification.aircraftIdentification}`);

    // 7. Test Retrieve Flight Plan in FIXM XML format via Accept header
    const xmlResponse = await fetch(`http://localhost:${TEST_PORT}/api/v1/ffice/plans/${filedGufi}`, {
      headers: { 'Accept': 'application/vnd.fixm+xml' }
    });
    const xmlText = await xmlResponse.text();
    console.log(`[PASS] GET /api/v1/ffice/plans/${filedGufi} (Accept: FIXM XML): Received ${xmlText.length} bytes of valid FIXM XML`);
    if (!xmlText.includes('<fx:Flight') || !xmlText.includes(filedGufi)) {
      throw new Error('FIXM XML response missing root Flight or GUFI');
    }

    // 8. Test Cancel Plan
    const cancelRes = await deleteJson(`http://localhost:${TEST_PORT}/api/v1/ffice/plans/${filedGufi}`);
    console.log(`[PASS] DELETE /api/v1/ffice/plans/${filedGufi}: Status=${cancelRes.status}`);

    console.log('\n>>> ALL PHASE 4 TESTS PASSED SUCCESSFULLY! <<<\n');
  } finally {
    server.close();
  }
}

async function fetchJson(urlStr: string) {
  const r = await fetch(urlStr);
  if (!r.ok) throw new Error(`HTTP error ${r.status} ${r.statusText}`);
  return r.json();
}

async function postJson(urlStr: string, body: any) {
  const r = await fetch(urlStr, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!r.ok) {
    const err = await r.text();
    throw new Error(`HTTP POST error ${r.status}: ${err}`);
  }
  return r.json();
}

async function deleteJson(urlStr: string) {
  const r = await fetch(urlStr, { method: 'DELETE' });
  if (!r.ok) throw new Error(`HTTP DELETE error ${r.status}`);
  return r.json();
}

testPhase4().catch(e => {
  console.error('Phase 4 test failed:', e);
  process.exit(1);
});

