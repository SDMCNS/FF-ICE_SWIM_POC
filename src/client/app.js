/**
 * FF-ICE Dispatch & Planning Console Front-End Application
 */

// Application State
const DEFAULT_AIRCRAFT_DATABASE = [
  { icaoType: 'A320', manufacturer: 'Airbus', model: 'A320-200 / neo', serviceCeilingFl: 390, ceiling: 390, typicalCruiseFl: 340, typicalFl: 340, cruiseTasKnots: 450, cruiseTas: 450, averageClimbRateFpm: 2200, climbRate: 2200, averageDescentRateFpm: 2000, descentRate: 2000, defaultEquipment: 'SDFGIRW/LB1', wakeTurbulenceCategory: 'MEDIUM', wake: 'M' },
  { icaoType: 'B738', manufacturer: 'Boeing', model: '737-800 / MAX 8', serviceCeilingFl: 410, ceiling: 410, typicalCruiseFl: 360, typicalFl: 360, cruiseTasKnots: 455, cruiseTas: 455, averageClimbRateFpm: 2300, climbRate: 2300, averageDescentRateFpm: 2000, descentRate: 2000, defaultEquipment: 'SDFGIRW/LB1', wakeTurbulenceCategory: 'MEDIUM', wake: 'M' },
  { icaoType: 'A321', manufacturer: 'Airbus', model: 'A321-200 / neo', serviceCeilingFl: 390, ceiling: 390, typicalCruiseFl: 350, typicalFl: 350, cruiseTasKnots: 455, cruiseTas: 455, averageClimbRateFpm: 2100, climbRate: 2100, averageDescentRateFpm: 2000, descentRate: 2000, defaultEquipment: 'SDFGIRW/LB1', wakeTurbulenceCategory: 'MEDIUM', wake: 'M' },
  { icaoType: 'E190', manufacturer: 'Embraer', model: 'E190 / E195-E2', serviceCeilingFl: 410, ceiling: 410, typicalCruiseFl: 340, typicalFl: 340, cruiseTasKnots: 430, cruiseTas: 430, averageClimbRateFpm: 2000, climbRate: 2000, averageDescentRateFpm: 1900, descentRate: 1900, defaultEquipment: 'SDFGIRW/LB1', wakeTurbulenceCategory: 'MEDIUM', wake: 'M' },
  { icaoType: 'AT76', manufacturer: 'ATR', model: '72-600', serviceCeilingFl: 250, ceiling: 250, typicalCruiseFl: 200, typicalFl: 200, cruiseTasKnots: 275, cruiseTas: 275, averageClimbRateFpm: 1200, climbRate: 1200, averageDescentRateFpm: 1500, descentRate: 1500, defaultEquipment: 'SDFGIR/S', wakeTurbulenceCategory: 'MEDIUM', wake: 'M' },
  { icaoType: 'DH8D', manufacturer: 'De Havilland', model: 'Dash 8 Q400', serviceCeilingFl: 270, ceiling: 270, typicalCruiseFl: 240, typicalFl: 240, cruiseTasKnots: 340, cruiseTas: 340, averageClimbRateFpm: 1500, climbRate: 1500, averageDescentRateFpm: 1600, descentRate: 1600, defaultEquipment: 'SDFGIR/S', wakeTurbulenceCategory: 'MEDIUM', wake: 'M' },
  { icaoType: 'B77W', manufacturer: 'Boeing', model: '777-300ER', serviceCeilingFl: 430, ceiling: 430, typicalCruiseFl: 370, typicalFl: 370, cruiseTasKnots: 490, cruiseTas: 490, averageClimbRateFpm: 2400, climbRate: 2400, averageDescentRateFpm: 2200, descentRate: 2200, defaultEquipment: 'SDFGIRW/LB1', wakeTurbulenceCategory: 'HEAVY', wake: 'H' },
  { icaoType: 'A359', manufacturer: 'Airbus', model: 'A350-900', serviceCeilingFl: 430, ceiling: 430, typicalCruiseFl: 380, typicalFl: 380, cruiseTasKnots: 490, cruiseTas: 490, averageClimbRateFpm: 2500, climbRate: 2500, averageDescentRateFpm: 2200, descentRate: 2200, defaultEquipment: 'SDFGIRW/LB1', wakeTurbulenceCategory: 'HEAVY', wake: 'H' },
  { icaoType: 'C172', manufacturer: 'Cessna', model: '172 Skyhawk', serviceCeilingFl: 140, ceiling: 140, typicalCruiseFl: 90, typicalFl: 90, cruiseTasKnots: 110, cruiseTas: 110, averageClimbRateFpm: 600, climbRate: 600, averageDescentRateFpm: 600, descentRate: 600, defaultEquipment: 'S/C', wakeTurbulenceCategory: 'LIGHT', wake: 'L' }
];

let gAirports = [];
let gWaypoints = [];
let gFirs = [];
let gAircraft = [...DEFAULT_AIRCRAFT_DATABASE];
let gSelectedWaypoints = [];
let gCurrentTrajectory = null;
let gCurrentPlan = null;
let gFiledPlans = [];
let gMap = null;
let gFlightPathLayer = null;
let gMarkersLayer = null;
let gFirLayers = [];
let gSpeedOverrideTas = null;

// Conflicting Paths Map Modal State
let gConflictsMap = null;
let gConflictsLayers = null;
let gCurrentDeconfliction = null;

// Weather Modal State
let gWeatherModalAirport = null;

// Map Waypoint Selector Modal State
let gWaypointSelectorMap = null;
let gModalWptLayer = null;
let gModalRouteLayer = null;
let gModalAirportsLayer = null;
let gModalWaypoints = [];
let gAllWaypointsCache = [];
let gModalMarkersMap = {};

document.addEventListener('DOMContentLoaded', async () => {
  initMap();
  initDefaultTime();
  initTabNavigation();
  await loadReferenceData();
  setupEventListeners();

  // Load default sample: EGLL -> EIDW
  loadSample('EGLL', 'EIDW', ['LIPGO'], 280, 'A320');
});

// --- Map Initialization ---
function initMap() {
  // Center over Irish Sea / UK
  gMap = L.map('airspaceMap').setView([53.8, -4.5], 6);

  // Standard OpenStreetMap tiles (100% free, no API key required)
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 18
  }).addTo(gMap);

  gFlightPathLayer = L.layerGroup().addTo(gMap);
  gMarkersLayer = L.layerGroup().addTo(gMap);
}

function initDefaultTime() {
  const now = new Date();
  now.setMinutes(now.getMinutes() + 30);
  document.getElementById('eobt').value = formatLocalDateTime(now);
  updateRunwayTimingRibbon();
}

function formatLocalDateTime(d) {
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function updateRunwayTimingRibbon() {
  const eobtVal = document.getElementById('eobt')?.value;
  const depIcao = document.getElementById('depAirport')?.value;
  const lblEtot = document.getElementById('lblDerivedEtot');
  const lblTaxi = document.getElementById('lblTaxiOut');
  const lblMode = document.getElementById('lblDepRunwayMode');

  if (!eobtVal || !lblEtot) return;

  const exot = (depIcao === 'EGLL') ? 20 : (depIcao === 'EIDW') ? 15 : (depIcao === 'EGCC' || depIcao === 'EGKK') ? 12 : 10;
  const mode = (depIcao === 'EGLL' || depIcao === 'EIDW' || depIcao === 'EGCC') ? 'PARALLEL_SEGREGATED' : 'MIXED_MODE_SINGLE';

  const eobtDate = new Date(eobtVal);
  const etotDate = new Date(eobtDate.getTime() + exot * 60 * 1000);
  const pad = n => String(n).padStart(2, '0');
  const etotStr = `${pad(etotDate.getUTCHours())}:${pad(etotDate.getUTCMinutes())} UTC`;

  lblEtot.textContent = etotStr;
  if (lblTaxi) lblTaxi.textContent = `${exot} min`;
  if (lblMode) {
    lblMode.textContent = mode;
    lblMode.style.background = mode === 'PARALLEL_SEGREGATED' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(245, 158, 11, 0.2)';
    lblMode.style.color = mode === 'PARALLEL_SEGREGATED' ? '#6ee7b7' : '#fcd34d';
    lblMode.style.borderColor = mode === 'PARALLEL_SEGREGATED' ? 'rgba(16, 185, 129, 0.4)' : 'rgba(245, 158, 11, 0.4)';
  }
}

// --- Tab Navigation ---
function initTabNavigation() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const targetId = btn.getAttribute('data-tab');
      const targetContent = document.getElementById(targetId);
      if (targetContent) targetContent.classList.add('active');

      if (targetId === 'tabMap') {
        setTimeout(() => gMap.invalidateSize(), 150);
      } else if (targetId === 'tabProfile' && gCurrentTrajectory) {
        renderVsdProfile(gCurrentTrajectory);
      }
    });
  });

  // FIXM XML/JSON sub-tabs
  document.getElementById('btnViewXml').addEventListener('click', (e) => {
    e.target.classList.add('active');
    document.getElementById('btnViewJson').classList.remove('active');
    updateFixmDisplay('XML');
  });

  document.getElementById('btnViewJson').addEventListener('click', (e) => {
    e.target.classList.add('active');
    document.getElementById('btnViewXml').classList.remove('active');
    updateFixmDisplay('JSON');
  });
}

// --- Normalization and Geometry Utilities ---
function normalizeAircraft(ac) {
  if (!ac) return null;
  const icaoType = (ac.icaoType || ac.icao || ac.type || ac.code || 'A320').toUpperCase();
  const manufacturer = ac.manufacturer || '';
  const model = ac.model || icaoType;
  const serviceCeilingFl = Number(ac.serviceCeilingFl ?? ac.ceiling ?? 390);
  const typicalCruiseFl = Number(ac.typicalCruiseFl ?? ac.typicalFl ?? (serviceCeilingFl > 350 ? 340 : Math.max(60, serviceCeilingFl - 30)));
  const cruiseTasKnots = Number(ac.cruiseTasKnots ?? ac.cruiseTas ?? 450);
  const averageClimbRateFpm = Number(ac.averageClimbRateFpm ?? ac.climbRate ?? 2200);
  const averageDescentRateFpm = Number(ac.averageDescentRateFpm ?? ac.descentRate ?? 2000);
  const defaultEquipment = ac.defaultEquipment || ac.equipment || 'SDFGIRW/LB1';
  const wakeCategory = (ac.wakeTurbulenceCategory || ac.wake || 'M').toUpperCase();

  return {
    ...ac,
    icaoType,
    manufacturer,
    model,
    serviceCeilingFl,
    ceiling: serviceCeilingFl,
    typicalCruiseFl,
    typicalFl: typicalCruiseFl,
    cruiseTasKnots,
    cruiseTas: cruiseTasKnots,
    averageClimbRateFpm,
    climbRate: averageClimbRateFpm,
    averageDescentRateFpm,
    descentRate: averageDescentRateFpm,
    defaultEquipment,
    equipment: defaultEquipment,
    wakeTurbulenceCategory: wakeCategory,
    wake: wakeCategory.charAt(0)
  };
}

function haversineDistanceNm(lat1, lon1, lat2, lon2) {
  const R = 3440.065; // Earth radius in NM
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function calculateBearingDeg(lat1, lon1, lat2, lon2) {
  const y = Math.sin((lon2 - lon1) * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180);
  const x = Math.cos(lat1 * Math.PI / 180) * Math.sin(lat2 * Math.PI / 180) -
            Math.sin(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.cos((lon2 - lon1) * Math.PI / 180);
  const brg = Math.atan2(y, x) * 180 / Math.PI;
  return (brg + 360) % 360;
}

function determineRecommendedFlightLevel() {
  const depIcao = document.getElementById('depAirport') ? document.getElementById('depAirport').value : '';
  const arrIcao = document.getElementById('arrAirport') ? document.getElementById('arrAirport').value : '';
  const acType = document.getElementById('aircraftType') ? (document.getElementById('aircraftType').value || 'A320').toUpperCase() : 'A320';
  const ac = gAircraft.find(a => (a.icaoType || '').toUpperCase() === acType) ||
             DEFAULT_AIRCRAFT_DATABASE.find(a => a.icaoType === acType) ||
             normalizeAircraft({ icaoType: acType });

  const ceiling = ac ? (ac.serviceCeilingFl || ac.ceiling || 390) : 390;
  let typical = ac ? (ac.typicalCruiseFl || ac.typicalFl || 340) : 340;

  const dep = gAirports.find(a => a.icao === depIcao);
  const arr = gAirports.find(a => a.icao === arrIcao);

  if (!dep || !arr) {
    if (typical > ceiling) typical = ceiling;
    return typical;
  }

  const distNm = haversineDistanceNm(dep.latitude, dep.longitude, arr.latitude, arr.longitude);
  const brg = calculateBearingDeg(dep.latitude, dep.longitude, arr.latitude, arr.longitude);
  const isEastbound = brg >= 0 && brg < 180;

  let recFl;
  if (distNm < 90) {
    recFl = isEastbound ? 110 : 100;
  } else if (distNm < 160) {
    recFl = isEastbound ? 170 : 160;
  } else if (distNm < 240) {
    recFl = isEastbound ? 250 : 240;
  } else if (distNm < 340) {
    recFl = isEastbound ? 290 : 280;
  } else {
    recFl = isEastbound ? (typical % 20 === 10 ? typical : typical + 10) : (typical % 20 === 0 ? typical : typical + 10);
  }

  // Cap at ceiling
  while (recFl > ceiling && recFl > 60) {
    recFl -= 20;
  }
  // Ensure semicircular consistency
  if (isEastbound && recFl % 20 === 0) {
    recFl = (recFl + 10 <= ceiling) ? recFl + 10 : recFl - 10;
  } else if (!isEastbound && recFl % 20 !== 0) {
    recFl = (recFl + 10 <= ceiling) ? recFl + 10 : recFl - 10;
  }

  return Math.max(60, Math.min(recFl, ceiling));
}

function updateSuggestedFlightLevel(autoApply = false) {
  const recFl = determineRecommendedFlightLevel();
  const badge = document.getElementById('suggestedFlBadge');
  if (badge) badge.textContent = `FL${recFl}`;
  if (autoApply) {
    const input = document.getElementById('cruiseFl');
    if (input) input.value = recFl;
  }
}

// --- Load Reference Data from SWIM Backend ---
async function loadReferenceData() {
  try {
    const [airportsRes, aircraftRes, firsRes] = await Promise.all([
      fetch('/api/v1/airports?limit=200').then(r => r.json()).catch(() => []),
      fetch('/api/v1/aircraft').then(r => r.json()).catch(() => []),
      fetch('/api/v1/airspace/fir').then(r => r.json()).catch(() => [])
    ]);

    if (airportsRes && (Array.isArray(airportsRes) || typeof airportsRes === 'object')) {
      gAirports = Array.isArray(airportsRes) ? airportsRes : Object.values(airportsRes);
    }
    if (aircraftRes && (Array.isArray(aircraftRes) || typeof aircraftRes === 'object')) {
      const rawList = Array.isArray(aircraftRes) ? aircraftRes : Object.values(aircraftRes);
      if (rawList.length > 0) {
        gAircraft = rawList.map(normalizeAircraft);
      }
    }
    if (firsRes && (Array.isArray(firsRes) || typeof firsRes === 'object')) {
      gFirs = Array.isArray(firsRes) ? firsRes : Object.values(firsRes);
    }

    populateAirportDropdowns();
    populateAircraftDropdown();
    renderFirAirspaces();
  } catch (err) {
    console.error('Error loading reference data from SWIM service:', err);
  }
}

function populateAirportDropdowns() {
  const depSelect = document.getElementById('depAirport');
  const arrSelect = document.getElementById('arrAirport');

  depSelect.innerHTML = '<option value="">-- Select Departure Aerodrome --</option>';
  arrSelect.innerHTML = '<option value="">-- Select Arrival Aerodrome --</option>';

  // Sort: Major hubs first, then alphabetical
  const sorted = [...gAirports].sort((a, b) => a.icao.localeCompare(b.icao));

  for (const a of sorted) {
    const opt1 = new Option(`${a.icao} - ${a.name} (${a.country})`, a.icao);
    const opt2 = new Option(`${a.icao} - ${a.name} (${a.country})`, a.icao);
    depSelect.add(opt1);
    arrSelect.add(opt2);
  }
}

function populateAircraftDropdown() {
  const select = document.getElementById('aircraftType');
  select.innerHTML = '';
  for (const ac of gAircraft) {
    const opt = new Option(`${ac.icaoType} - ${ac.manufacturer} ${ac.model}`, ac.icaoType);
    select.add(opt);
  }
  updateAircraftPerfBadge();
}

function updateAircraftPerfBadge() {
  gSpeedOverrideTas = null;
  const type = (document.getElementById('aircraftType').value || 'A320').toUpperCase();
  const ac = gAircraft.find(a => (a.icaoType || '').toUpperCase() === type) ||
             DEFAULT_AIRCRAFT_DATABASE.find(a => a.icaoType === type) ||
             normalizeAircraft({ icaoType: type });
  if (!ac) return;

  const ceiling = ac.serviceCeilingFl ?? ac.ceiling ?? 390;
  const climb = ac.averageClimbRateFpm ?? ac.climbRate ?? 2200;
  const tas = ac.cruiseTasKnots ?? ac.cruiseTas ?? 450;
  const descent = ac.averageDescentRateFpm ?? ac.descentRate ?? 2000;
  const equip = ac.defaultEquipment ?? ac.equipment ?? 'SDFGIRW/LB1';

  document.getElementById('perfCeiling').textContent = `FL${ceiling}`;
  document.getElementById('perfClimb').textContent = `${climb} fpm`;
  document.getElementById('perfTas').textContent = `${tas} kts`;
  document.getElementById('perfDescent').textContent = `${descent} fpm`;
  document.getElementById('equipment').value = equip;

  updateSuggestedFlightLevel(false);
}

// --- Render 3D FIR Airspaces on Map ---
function renderFirAirspaces() {
  const firColors = {
    EGTTFIR: { stroke: '#38bdf8', fill: 'rgba(56, 189, 248, 0.08)' },
    EGTTUIR: { stroke: '#0284c7', fill: 'rgba(2, 132, 199, 0.05)' },
    EGPXFIR: { stroke: '#c084fc', fill: 'rgba(192, 132, 252, 0.08)' },
    EGPXUIR: { stroke: '#9333ea', fill: 'rgba(147, 51, 234, 0.05)' },
    EISNFIR: { stroke: '#4ade80', fill: 'rgba(74, 222, 128, 0.08)' },
    EISNUIR: { stroke: '#16a34a', fill: 'rgba(22, 163, 74, 0.05)' },
    EGGXFIR: { stroke: '#fb923c', fill: 'rgba(251, 146, 60, 0.05)' }
  };

  for (const fir of gFirs) {
    // Only draw lower FIRs for 2D boundary clarity (UIRs share identical horizontal polygon bounds)
    if (fir.airspaceId.includes('UIR')) continue;

    const latlngs = fir.vertices.map(v => [v.latitude, v.longitude]);
    const styling = firColors[fir.airspaceId] || { stroke: '#94a3b8', fill: 'rgba(148, 163, 184, 0.05)' };

    const poly = L.polygon(latlngs, {
      color: styling.stroke,
      weight: 1.5,
      fillColor: styling.fill,
      fillOpacity: 0.15,
      dashArray: '3, 4'
    }).addTo(gMap);

    poly.bindPopup(`<strong>${fir.airspaceId}</strong><br>Vertical Limits: FL${fir.minFlightLevel} to FL${fir.maxFlightLevel}<br>Jurisdiction: ${fir.country === 'IE' ? 'Irish Aviation Authority' : 'NATS UK'}`);
    gFirLayers.push(poly);
  }
}

// --- Event Listeners ---
function setupEventListeners() {
  document.getElementById('aircraftType').addEventListener('change', () => {
    updateAircraftPerfBadge();
    updateSuggestedFlightLevel(false);
    refreshDepartureSlots();
  });

  document.getElementById('depAirport').addEventListener('change', e => {
    updateRunwayOptions(e.target.value, 'depRunway');
    updateSuggestedFlightLevel(false);
    updateRunwayTimingRibbon();
    refreshDepartureSlots();
  });

  document.getElementById('arrAirport').addEventListener('change', e => {
    updateRunwayOptions(e.target.value, 'arrRunway');
    updateSuggestedFlightLevel(false);
  });

  const btnSuggest = document.getElementById('btnAutoSuggestFl');
  if (btnSuggest) {
    btnSuggest.addEventListener('click', () => {
      updateSuggestedFlightLevel(true);
      calculateTrajectory();
    });
  }

  document.getElementById('eobt').addEventListener('input', updateRunwayTimingRibbon);
  document.getElementById('eobt').addEventListener('change', () => {
    updateRunwayTimingRibbon();
    refreshDepartureSlots();
  });

  const depSlotSel = document.getElementById('depSlotSelect');
  if (depSlotSel) {
    depSlotSel.addEventListener('change', e => {
      const val = e.target.value;
      if (val) {
        document.getElementById('eobt').value = formatLocalDateTime(new Date(val));
        const badge = document.getElementById('depSlotBadge');
        if (badge) {
          badge.className = 'slot-badge available';
          badge.textContent = `Allocated ${val.substring(11, 16)} UTC`;
        }
        calculateTrajectory();
      }
    });
  }

  const btnOpenSlots = document.getElementById('btnOpenSlotModal');
  if (btnOpenSlots) {
    btnOpenSlots.addEventListener('click', openSlotBoardModal);
  }

  const btnRefreshSlots = document.getElementById('btnRefreshSlotModal');
  if (btnRefreshSlots) {
    btnRefreshSlots.addEventListener('click', loadAndRenderSlotBoard);
  }

  ['slotModalAirport', 'slotModalType', 'slotModalDate'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', loadAndRenderSlotBoard);
  });

  document.getElementById('btnNowPlus30').addEventListener('click', () => {
    initDefaultTime();
    refreshDepartureSlots();
  });

  // Quick Samples
  document.getElementById('btnSampleEGLL_EIDW').addEventListener('click', () => {
    loadSample('EGLL', 'EIDW', ['LIPGO'], 280, 'A320');
  });

  document.getElementById('btnSampleEGPH_EICK').addEventListener('click', () => {
    loadSample('EGPH', 'EICK', ['LIPGO'], 300, 'B738');
  });

  document.getElementById('btnSampleEINN_EGKK').addEventListener('click', () => {
    loadSample('EINN', 'EGKK', ['LIPGO'], 290, 'A320');
  });

  // Waypoints
  document.getElementById('btnAddWaypoint').addEventListener('click', addWaypointFromSearch);
  document.getElementById('waypointSearch').addEventListener('keydown', e => {
    if (e.key === 'Enter') addWaypointFromSearch();
  });
  document.getElementById('btnClearWaypoints').addEventListener('click', () => {
    gSelectedWaypoints = [];
    renderWaypointChips();
  });

  // Airway buttons
  document.querySelectorAll('.btn-airway').forEach(btn => {
    btn.addEventListener('click', () => {
      const route = btn.getAttribute('data-route');
      insertAirwayWaypoints(route);
    });
  });

  // Trajectory Calculation
  document.getElementById('btnCalculate').addEventListener('click', calculateTrajectory);

  // Dedicated 4D Conflict Test Button
  document.getElementById('btnTestConflicts').addEventListener('click', test4DConflicts);

  // File Plan
  document.getElementById('btnFilePlan').addEventListener('click', fileFlightPlan);

  // Modals event setup
  setupModals();

  // Export buttons
  document.getElementById('btnExportXml').addEventListener('click', () => downloadFile('fixm_flightplan.xml', getFixmXmlString(), 'application/vnd.fixm+xml'));
  document.getElementById('btnExportJson').addEventListener('click', () => downloadFile('fixm_flightplan.json', JSON.stringify(gCurrentPlan || {}, null, 2), 'application/json'));

  document.getElementById('btnCopyFixm').addEventListener('click', () => {
    const text = document.getElementById('fixmOutput').textContent;
    navigator.clipboard.writeText(text);
    alert('FIXM payload copied to clipboard!');
  });

  // Weather & Active Runways Modal Triggers
  const btnWeather = document.getElementById('btnOpenWeatherModal');
  if (btnWeather) {
    btnWeather.addEventListener('click', () => {
      const curDep = document.getElementById('depAirport').value || 'EGLL';
      document.getElementById('weatherInfoModal').classList.remove('hidden');
      loadWeatherModal(curDep);
    });
  }

  document.querySelectorAll('.weather-quick-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const icao = btn.getAttribute('data-icao');
      loadWeatherModal(icao);
    });
  });

  const btnFetchWeather = document.getElementById('btnFetchWeatherModal');
  if (btnFetchWeather) {
    btnFetchWeather.addEventListener('click', () => {
      const input = document.getElementById('weatherIcaoInput');
      if (input && input.value) {
        loadWeatherModal(input.value.trim());
      }
    });
  }

  const weatherInput = document.getElementById('weatherIcaoInput');
  if (weatherInput) {
    weatherInput.addEventListener('keydown', e => {
      if (e.key === 'Enter' && weatherInput.value) {
        loadWeatherModal(weatherInput.value.trim());
      }
    });
  }

  // Conflicting Paths Map Modal Trigger
  const btnOpenConflicts = document.getElementById('btnOpenConflictsMap');
  if (btnOpenConflicts) {
    btnOpenConflicts.addEventListener('click', openConflictsMapModal);
  }

  // Filed Plans Lifecycle & Pruning Controls
  const chkShowAll = document.getElementById('chkShowAllPlans');
  if (chkShowAll) {
    chkShowAll.addEventListener('change', () => refreshFiledPlans());
  }
  const btnRefreshFiled = document.getElementById('btnRefreshPlans');
  if (btnRefreshFiled) {
    btnRefreshFiled.addEventListener('click', () => refreshFiledPlans());
  }
  const btnSweepStale = document.getElementById('btnSweepStalePlans');
  if (btnSweepStale) {
    btnSweepStale.addEventListener('click', () => sweepStalePlansNow());
  }

  // Automated background poll for filed plans every 30 seconds
  setInterval(() => {
    refreshFiledPlans();
  }, 30000);
}


async function updateRunwayOptions(airportIcao, selectId) {
  const select = document.getElementById(selectId);
  const badgeId = selectId === 'depRunway' ? 'depWeatherBadge' : 'arrWeatherBadge';
  const badge = document.getElementById(badgeId);

  select.innerHTML = '<option value="">Loading runways & wind...</option>';
  if (badge) {
    badge.textContent = `💨 Fetching live NOAA METAR for ${airportIcao}...`;
    badge.classList.remove('highlight');
  }

  if (!airportIcao) return;

  try {
    const res = await fetch(`/api/v1/weather/metar?icao=${encodeURIComponent(airportIcao)}`).then(r => r.json());
    const activeInfo = res.activeRunway || {};
    const metar = res.metar || {};

    if (badge) {
      if (metar.rawOb) {
        badge.textContent = `💨 METAR: ${metar.rawOb}`;
        badge.title = activeInfo.explanation || metar.rawOb;
        badge.classList.add('highlight');
      } else {
        badge.textContent = `💨 ${activeInfo.windSummary || 'Calm Wind'} • Active: RWY ${activeInfo.activeRunway}`;
      }
    }

    select.innerHTML = '';
    const activeDes = activeInfo.activeRunway || 'AUTO';
    const activeLabel = `Auto (Active: RWY ${activeDes} - ${activeInfo.headwindKnots >= 0 ? '+' : ''}${activeInfo.headwindKnots}kt HW)`;
    select.add(new Option(activeLabel, activeDes));

    const allRunways = activeInfo.allRunways || [];
    for (const r of allRunways) {
      const hwText = r.headwind >= 0 ? `+${r.headwind}kt HW` : `${r.headwind}kt TW`;
      const optLabel = `RWY ${r.designator} (${hwText}, ${Math.abs(r.crosswind)}kt XW)${r.isActive ? ' ★ ACTIVE' : ''}`;
      const opt = new Option(optLabel, r.designator);
      select.add(opt);
    }

    select.value = activeDes;
  } catch (err) {
    console.error('Weather/runway fetch error:', err);
    select.innerHTML = '<option value="">Auto (Active Runway)</option>';
    const airport = gAirports.find(a => a.icao === airportIcao);
    if (airport && airport.runways) {
      for (const r of airport.runways) {
        select.add(new Option(`RWY ${r.designator}`, r.designator));
      }
    }
  }
}

async function loadSample(dep, arr, waypoints, fl, acType) {
  document.getElementById('depAirport').value = dep;
  document.getElementById('arrAirport').value = arr;
  document.getElementById('aircraftType').value = acType;
  updateAircraftPerfBadge();
  updateRunwayTimingRibbon();

  const initialFl = fl || determineRecommendedFlightLevel();
  document.getElementById('cruiseFl').value = initialFl;
  updateSuggestedFlightLevel(false);

  gSelectedWaypoints = [...waypoints];
  renderWaypointChips();

  await Promise.all([
    updateRunwayOptions(dep, 'depRunway'),
    updateRunwayOptions(arr, 'arrRunway'),
    refreshDepartureSlots()
  ]);

  calculateTrajectory();
}

// --- Waypoint Management ---
async function addWaypointFromSearch() {
  const input = document.getElementById('waypointSearch');
  const name = input.value.trim().toUpperCase();
  if (!name) return;

  try {
    const res = await fetch(`/api/v1/waypoints?query=${encodeURIComponent(name)}&limit=1`).then(r => r.json());
    if (res && res.length > 0) {
      const match = res[0];
      if (!gSelectedWaypoints.includes(match.name)) {
        gSelectedWaypoints.push(match.name);
        renderWaypointChips();
      }
      input.value = '';
    } else {
      alert(`Waypoint "${name}" not found in UK or Irish aeronautical databases.`);
    }
  } catch (err) {
    console.error(err);
  }
}

function insertAirwayWaypoints(airwayCode) {
  const presets = {
    L18: ['SUROX', 'LIPGO'],
    L149: ['OLAPO', 'PESIT'],
    L975: ['SHA', 'RIKUL']
  };

  const wps = presets[airwayCode] || [];
  for (const w of wps) {
    if (!gSelectedWaypoints.includes(w)) gSelectedWaypoints.push(w);
  }
  renderWaypointChips();
}

function renderWaypointChips() {
  const container = document.getElementById('waypointChips');
  container.innerHTML = '';

  if (gSelectedWaypoints.length === 0) {
    container.innerHTML = '<span class="subtext" style="padding: 4px;">Direct flight path (no en-route waypoints selected)</span>';
    return;
  }

  gSelectedWaypoints.forEach((name, idx) => {
    const chip = document.createElement('div');
    chip.className = 'waypoint-chip draggable-chip';
    chip.draggable = true;
    chip.dataset.index = idx;
    chip.title = 'Drag to reorder waypoint sequence in flight plan';
    chip.innerHTML = `
      <span class="drag-grip" title="Drag to reorder">⋮⋮</span>
      <span>${idx + 1}. ${name}</span>
      <span class="chip-remove" onclick="removeWaypoint(${idx})" title="Remove">&times;</span>
    `;

    chip.addEventListener('dragstart', e => {
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', idx.toString());
      chip.classList.add('dragging');
    });

    chip.addEventListener('dragend', () => {
      chip.classList.remove('dragging');
      container.querySelectorAll('.draggable-chip').forEach(c => c.classList.remove('drag-over-left', 'drag-over-right'));
    });

    chip.addEventListener('dragover', e => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      const rect = chip.getBoundingClientRect();
      const midX = rect.left + rect.width / 2;
      if (e.clientX < midX) {
        chip.classList.add('drag-over-left');
        chip.classList.remove('drag-over-right');
      } else {
        chip.classList.add('drag-over-right');
        chip.classList.remove('drag-over-left');
      }
    });

    chip.addEventListener('dragleave', () => {
      chip.classList.remove('drag-over-left', 'drag-over-right');
    });

    chip.addEventListener('drop', e => {
      e.preventDefault();
      chip.classList.remove('drag-over-left', 'drag-over-right');
      const fromIdx = parseInt(e.dataTransfer.getData('text/plain'), 10);
      if (isNaN(fromIdx) || fromIdx === idx) return;

      const rect = chip.getBoundingClientRect();
      const midX = rect.left + rect.width / 2;
      let toIdx = e.clientX < midX ? idx : idx + 1;
      if (fromIdx < toIdx) toIdx--;

      const moved = gSelectedWaypoints.splice(fromIdx, 1)[0];
      gSelectedWaypoints.splice(toIdx, 0, moved);
      renderWaypointChips();
      calculateTrajectory();
    });

    container.appendChild(chip);
  });
}

window.removeWaypoint = function(idx) {
  gSelectedWaypoints.splice(idx, 1);
  renderWaypointChips();
};

// --- Calculate 4D Trajectory ---
async function calculateTrajectory() {
  const dep = document.getElementById('depAirport').value;
  const arr = document.getElementById('arrAirport').value;
  const fl = parseInt(document.getElementById('cruiseFl').value, 10);
  const acType = document.getElementById('aircraftType').value;
  const eobt = document.getElementById('eobt').value;

  if (!dep || !arr) {
    alert('Please select both departure and arrival aerodromes.');
    return;
  }

  if (dep === arr) {
    alert('Departure and arrival aerodromes cannot be identical.');
    return;
  }

  try {
    const payload = {
      departureIcao: dep,
      departureRunway: document.getElementById('depRunway').value || undefined,
      arrivalIcao: arr,
      arrivalRunway: document.getElementById('arrRunway').value || undefined,
      aircraftType: acType,
      requestedCruiseFl: fl,
      waypointNames: gSelectedWaypoints,
      estimatedOffBlockTime: eobt ? new Date(eobt).toISOString() : new Date().toISOString(),
      cruiseTasOverride: gSpeedOverrideTas || undefined
    };

    const res = await fetch('/api/v1/trajectory/calculate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(r => r.json());

    if (res.error) {
      alert(`Calculation error: ${res.error}`);
      return;
    }

    gCurrentTrajectory = res.calculated;
    displaySanityAdvisory(res.calculated.sanityResult);
    if (res.calculated.deconfliction) {
      displayDeconflictionAdvisory(res.calculated.deconfliction);
    }
    updateArrivalSlotStatus(res.calculated);
    renderFlightPlanOnMap(res.calculated);
    renderVsdProfile(res.calculated);
    renderPointsTable(res.calculated.points);
    buildCurrentPlanObject(res);
    updateFixmDisplay('XML');
  } catch (err) {
    console.error('Calculation error:', err);
    alert('Failed to calculate 4D trajectory.');
  }
}

// --- Display Sanity Advisory Banner ---
function displaySanityAdvisory(sanity) {
  const banner = document.getElementById('sanityBanner');
  const icon = document.getElementById('sanityIcon');
  const title = document.getElementById('sanityTitle');
  const msgs = document.getElementById('sanityMessages');
  const btnApply = document.getElementById('btnApplyAdvisory');

  banner.classList.remove('hidden', 'success', 'warning', 'error');
  btnApply.classList.add('hidden');

  if (sanity.errors && sanity.errors.length > 0) {
    banner.classList.add('error');
    icon.textContent = '❌';
    title.textContent = 'Trajectory Invalidation / Service Ceiling Exceeded';
    msgs.innerHTML = sanity.errors.map(e => `<div>&bull; ${e}</div>`).join('');
  } else if (sanity.warnings && sanity.warnings.length > 0) {
    banner.classList.add('warning');
    icon.textContent = '⚠️';
    title.textContent = 'Sanity Advisory: Unachievable or Non-Conforming Cruise Flight Level';
    msgs.innerHTML = sanity.warnings.map(w => `<div>&bull; ${w}</div>`).join('');

    if (sanity.recommendedCruiseFl && sanity.recommendedCruiseFl !== parseInt(document.getElementById('cruiseFl').value, 10)) {
      btnApply.classList.remove('hidden');
      btnApply.textContent = `Apply Recommended Level: FL${sanity.recommendedCruiseFl}`;
      btnApply.onclick = () => {
        document.getElementById('cruiseFl').value = sanity.recommendedCruiseFl;
        calculateTrajectory();
      };
    }
  } else {
    banner.classList.add('success');
    icon.textContent = '✅';
    title.textContent = 'Sanity Check Passed: Realistic & Semicircular Compliant';
    msgs.innerHTML = `<div>&bull; Total distance: ${sanity.totalRouteDistanceNm.toFixed(1)} NM &bull; Required transition distance: ${sanity.minimumRequiredDistanceNm.toFixed(1)} NM</div>`;
  }
}

// --- Display 4D Strategic Deconfliction Banner ---
function displayDeconflictionAdvisory(deconf) {
  gCurrentDeconfliction = deconf;
  const banner = document.getElementById('deconflictionBanner');
  const icon = document.getElementById('deconflictionIcon');
  const title = document.getElementById('deconflictionTitle');
  const msgs = document.getElementById('deconflictionMessages');
  const btnOpenMap = document.getElementById('btnOpenConflictsMap');
  const compContainer = document.getElementById('comprehensiveSolutionsContainer');
  const resContainer = document.getElementById('deconflictionResolutions');

  banner.classList.remove('hidden', 'clear', 'conflict');
  resContainer.innerHTML = '';
  if (compContainer) compContainer.innerHTML = '';

  if (deconf.hasConflicts) {
    banner.classList.add('conflict');
    icon.textContent = '⚠️';
    title.textContent = `4D Separation Alert (${deconf.conflictCount} Conflict${deconf.conflictCount > 1 ? 's' : ''} in Database)`;
    msgs.innerHTML = `<div>&bull; Separation minimums violated: En-route &lt; 5.0 NM (when vertical &lt; 1,000 ft), approach &lt; 3.0 NM / wake separation, or runway wake intervals (ICAO Doc 4444).</div>`;
    if (btnOpenMap) btnOpenMap.classList.remove('hidden');

    // 1. Render Global Comprehensive Solutions (Resolves ALL conflicts simultaneously)
    if (compContainer && deconf.comprehensiveSolutions && deconf.comprehensiveSolutions.length > 0) {
      let compHtml = `
        <div style="font-size: 0.76rem; font-weight: 800; color: #6ee7b7; text-transform: uppercase; letter-spacing: 0.4px; margin-bottom: 4px;">
          ✨ Comprehensive Solution Recommendations (Resolves ALL ${deconf.conflictCount} Conflicts Simultaneously):
        </div>
      `;

      deconf.comprehensiveSolutions.forEach((sol, idx) => {
        const isTop = idx === 0;
        const badgesHtml = (sol.badges || []).map(b => `<span class="comp-badge ${b.includes('All') ? 'green' : ''}">${b}</span>`).join('');
        compHtml += `
          <div class="comprehensive-card ${isTop ? 'top-choice' : ''}">
            <div class="comp-header">
              <span class="comp-title">
                ${isTop ? '⭐ Recommended: ' : ''}${sol.title}
              </span>
              <span class="comp-efficiency-pill">${sol.efficiencyScore}% Efficiency</span>
            </div>
            <div class="comp-desc">${sol.description}</div>
            <div class="comp-badges-row">${badgesHtml}</div>
            <button type="button" class="comp-apply-btn" onclick="applyComprehensiveSolution('${sol.id}')">
              ⚡ Apply Solution (Resolves All Traffic)
            </button>
          </div>
        `;
      });
      compContainer.innerHTML = compHtml;
    }

    // 2. Render Tactical Per-Conflict Breakdown Cards
    let cardsHtml = '';
    for (const c of deconf.conflicts) {
      let suggestionsHtml = '';
      if (c.suggestions && c.suggestions.length > 0) {
        suggestionsHtml = `
          <div class="suggestion-actions-title">Tactical Options for this Flight:</div>
          <div class="suggestion-actions-grid">
            ${c.suggestions.map(s => {
              if (s.action === 'SET_ALTITUDE') {
                return `<button type="button" class="btn-suggestion btn-suggestion-alt" onclick="applyDeconflictionSuggestion('SET_ALTITUDE', { level: ${s.targetFlightLevel} })" title="${s.description}">⚡ ${s.title}</button>`;
              } else if (s.action === 'ADJUST_EOBT') {
                return `<button type="button" class="btn-suggestion btn-suggestion-delay" onclick="applyDeconflictionSuggestion('ADJUST_EOBT', { minutes: ${s.delayMinutes || 10} })" title="${s.description}">⏱️ ${s.title}</button>`;
              } else if (s.action === 'REPLACE_WAYPOINT') {
                return `<button type="button" class="btn-suggestion btn-suggestion-reroute" onclick="applyDeconflictionSuggestion('REPLACE_WAYPOINT', { oldWp: '${s.oldWaypoint}', newWp: '${s.newWaypoint}' })" title="${s.description}">🔀 ${s.title}</button>`;
              } else if (s.action === 'ADJUST_SPEED') {
                return `<button type="button" class="btn-suggestion btn-suggestion-speed" onclick="applyDeconflictionSuggestion('ADJUST_SPEED', { delta: ${s.speedDeltaKnots || -30} })" title="${s.description}">🐢 ${s.title}</button>`;
              }
              return '';
            }).join('')}
          </div>
        `;
      }

      cardsHtml += `
        <div class="conflict-card">
          <div class="conflict-card-header">
            <span>🚨 Conflicting Flight: <strong>${c.conflictingCallsign}</strong></span>
            <span>CPA ${c.timeOfClosestApproach.substring(11, 19)} UTC</span>
          </div>
          <div class="conflict-card-desc">
            ${c.description}
          </div>
          ${suggestionsHtml}
        </div>
      `;
    }

    resContainer.innerHTML = cardsHtml;
  } else {
    banner.classList.add('clear');
    icon.textContent = '🛡️';
    title.textContent = '4D Strategic Deconfliction: Clear';
    if (btnOpenMap) btnOpenMap.classList.add('hidden');
    msgs.innerHTML = `
      <div>&bull; Airspace deconflicted! Zero loss of separation detected against active database flight plans.</div>
      <div style="margin-top: 8px;">
        <button type="button" class="btn-file-clear" onclick="fileFlightPlan()">📤 File FF-ICE Plan (SWIM)</button>
      </div>
    `;
  }
}

// Global Comprehensive Solution Applicator
window.applyComprehensiveSolution = function(solId) {
  if (!gCurrentDeconfliction || !gCurrentDeconfliction.comprehensiveSolutions) return;
  const sol = gCurrentDeconfliction.comprehensiveSolutions.find(s => s.id === solId);
  if (!sol) return;

  for (const act of (sol.actions || [])) {
    if (act.type === 'SET_ALTITUDE') {
      const flSelect = document.getElementById('cruiseFl');
      if (flSelect) flSelect.value = act.targetFlightLevel;
    } else if (act.type === 'ADJUST_EOBT') {
      const eobtInput = document.getElementById('eobt');
      const cur = eobtInput.value ? new Date(eobtInput.value) : new Date();
      cur.setMinutes(cur.getMinutes() + (act.delayMinutes || 10));
      eobtInput.value = formatLocalDateTime(cur);
    } else if (act.type === 'ADJUST_SPEED') {
      const acType = document.getElementById('aircraftType').value;
      const ac = gAircraft.find(a => a.icaoType === acType) || { cruiseTasKnots: 450 };
      const curSpd = gSpeedOverrideTas || ac.cruiseTasKnots || 450;
      gSpeedOverrideTas = Math.max(180, curSpd + (act.speedDeltaKnots || -30));
      const perfTasSpan = document.getElementById('perfTas');
      if (perfTasSpan) perfTasSpan.textContent = `${gSpeedOverrideTas} kts (Longitudinal Control)`;
    } else if (act.type === 'REPLACE_WAYPOINT') {
      const oldWp = (act.oldWaypoint || '').toUpperCase();
      const newWp = (act.newWaypoint || '').toUpperCase();
      const idx = gSelectedWaypoints.indexOf(oldWp);
      if (idx !== -1) gSelectedWaypoints[idx] = newWp;
      else gSelectedWaypoints.push(newWp);
      renderWaypointChips();
    }
  }

  // Recalculate 4D trajectory and auto-test conflicts
  calculateTrajectory();
};

// Global Suggestion Applicator for Interactive Deconfliction Loop
window.applyDeconflictionSuggestion = function(action, params) {
  if (action === 'SET_ALTITUDE') {
    document.getElementById('cruiseFl').value = params.level;
  } else if (action === 'ADJUST_EOBT') {
    const eobtInput = document.getElementById('eobt');
    const cur = eobtInput.value ? new Date(eobtInput.value) : new Date();
    cur.setMinutes(cur.getMinutes() + (params.minutes || 10));
    eobtInput.value = formatLocalDateTime(cur);
  } else if (action === 'REPLACE_WAYPOINT') {
    const oldWp = (params.oldWp || '').toUpperCase();
    const newWp = (params.newWp || '').toUpperCase();
    const idx = gSelectedWaypoints.indexOf(oldWp);
    if (idx !== -1) {
      gSelectedWaypoints[idx] = newWp;
    } else {
      gSelectedWaypoints.push(newWp);
    }
    renderWaypointChips();
  } else if (action === 'ADJUST_SPEED') {
    const acType = document.getElementById('aircraftType').value;
    const ac = gAircraft.find(a => a.icaoType === acType) || { cruiseTasKnots: 450 };
    const curSpd = gSpeedOverrideTas || ac.cruiseTasKnots || 450;
    gSpeedOverrideTas = Math.max(180, curSpd + (params.delta || -30));
    const perfTasSpan = document.getElementById('perfTas');
    if (perfTasSpan) perfTasSpan.textContent = `${gSpeedOverrideTas} kts (Longitudinal Control)`;
  }

  // Recalculate 4D trajectory and auto-test conflicts
  calculateTrajectory();
};

// --- Render Flightpath on Leaflet Map ---
function renderFlightPlanOnMap(calc) {
  gFlightPathLayer.clearLayers();
  gMarkersLayer.clearLayers();

  const latlngs = calc.points.map(p => [p.coordinates.latitude, p.coordinates.longitude]);

  // Polyline for flightpath
  const poly = L.polyline(latlngs, {
    color: '#f59e0b',
    weight: 3.5,
    opacity: 0.9
  }).addTo(gFlightPathLayer);

  // Add markers
  calc.points.forEach((pt, i) => {
    let color = '#38bdf8';
    let radius = 5;

    if (pt.pointType === 'DEPARTURE' || pt.pointType === 'DESTINATION') {
      color = '#10b981';
      radius = 8;
    } else if (pt.pointType === 'INITIAL_CLIMB') {
      color = '#22c55e';
      radius = 7;
    } else if (pt.pointType === 'APPROACH_INTERCEPT') {
      color = '#eab308';
      radius = 7;
    } else if (pt.pointType === 'TOC' || pt.pointType === 'TOD') {
      color = '#06b6d4';
      radius = 6;
    } else if (pt.pointType === 'FIR_CROSSING') {
      color = '#c084fc';
      radius = 6;
    }

    let detailNote = '';
    if (pt.pointType === 'INITIAL_CLIMB') {
      detailNote = '<strong>Corridor:</strong> Initial climb-out (No turning for 5 NM post-takeoff)<br>';
    } else if (pt.pointType === 'APPROACH_INTERCEPT') {
      detailNote = '<strong>Approach:</strong> 17 NM ILS localizer intercept & stabilized 3° glidepath<br>';
    }

    const circle = L.circleMarker([pt.coordinates.latitude, pt.coordinates.longitude], {
      color,
      fillColor: color,
      fillOpacity: 0.9,
      radius
    }).addTo(gMarkersLayer);

    circle.bindPopup(`
      <strong>${pt.identifier} (${pt.pointType})</strong><br>
      ${detailNote}
      Level: FL${pt.flightLevel} (${pt.altitudeFeet.toLocaleString()} ft)<br>
      Cumulative: ${pt.cumulativeDistanceNm} NM<br>
      ETA: ${pt.estimatedTimestamp.substring(11, 19)} UTC<br>
      Airspace: ${pt.associatedAirspace || 'N/A'}
    `);
  });

  gMap.fitBounds(poly.getBounds().pad(0.15));
}

// --- Vertical Situation Display (VSD Canvas) ---
function renderVsdProfile(calc) {
  const canvas = document.getElementById('vsdCanvas');
  const ctx = canvas.getContext('2d');
  const W = canvas.width;
  const H = canvas.height;

  ctx.clearRect(0, 0, W, H);

  // Background
  ctx.fillStyle = '#0b1120';
  ctx.fillRect(0, 0, W, H);

  const paddingLeft = 60;
  const paddingRight = 40;
  const paddingTop = 30;
  const paddingBottom = 45;

  const plotW = W - paddingLeft - paddingRight;
  const plotH = H - paddingTop - paddingBottom;

  const maxAlt = 42000;
  const totalDist = calc.totalDistanceNm;

  function xFromDist(d) {
    return paddingLeft + (d / totalDist) * plotW;
  }

  function yFromAlt(a) {
    return paddingTop + (1 - (a / maxAlt)) * plotH;
  }

  // Draw Altitude Grid Lines (every 5000 ft)
  ctx.strokeStyle = '#1e293b';
  ctx.lineWidth = 1;
  ctx.fillStyle = '#64748b';
  ctx.font = '10px monospace';
  ctx.textAlign = 'right';

  for (let alt = 0; alt <= maxAlt; alt += 5000) {
    const y = yFromAlt(alt);
    ctx.beginPath();
    ctx.moveTo(paddingLeft, y);
    ctx.lineTo(W - paddingRight, y);
    ctx.stroke();

    const fl = Math.round(alt / 100);
    ctx.fillText(`FL${String(fl).padStart(3, '0')}`, paddingLeft - 8, y + 3);
  }

  // Draw Lower/Upper Airspace Boundary Line at FL245 (24,500 ft)
  const yFl245 = yFromAlt(24500);
  ctx.strokeStyle = '#475569';
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(paddingLeft, yFl245);
  ctx.lineTo(W - paddingRight, yFl245);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = '#94a3b8';
  ctx.textAlign = 'left';
  ctx.fillText('Upper Airspace (UIR) Boundary FL245', paddingLeft + 10, yFl245 - 4);

  // Draw Distance Axis
  ctx.strokeStyle = '#334155';
  ctx.beginPath();
  ctx.moveTo(paddingLeft, H - paddingBottom);
  ctx.lineTo(W - paddingRight, H - paddingBottom);
  ctx.stroke();

  ctx.fillStyle = '#64748b';
  ctx.textAlign = 'center';
  for (let dist = 0; dist <= totalDist; dist += 50) {
    const x = xFromDist(dist);
    ctx.fillText(`${dist} NM`, x, H - paddingBottom + 16);
  }
  ctx.fillText(`${totalDist.toFixed(1)} NM`, xFromDist(totalDist), H - paddingBottom + 16);

  // Draw Altitude Profile Path
  ctx.beginPath();
  calc.points.forEach((pt, i) => {
    const x = xFromDist(pt.cumulativeDistanceNm);
    const y = yFromAlt(pt.altitudeFeet);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = '#38bdf8';
  ctx.lineWidth = 3;
  ctx.stroke();

  // Fill gradient under flight profile
  ctx.lineTo(xFromDist(totalDist), H - paddingBottom);
  ctx.lineTo(paddingLeft, H - paddingBottom);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, paddingTop, 0, H - paddingBottom);
  grad.addColorStop(0, 'rgba(56, 189, 248, 0.25)');
  grad.addColorStop(1, 'rgba(56, 189, 248, 0.01)');
  ctx.fillStyle = grad;
  ctx.fill();

  // Draw points & labels
  calc.points.forEach(pt => {
    const x = xFromDist(pt.cumulativeDistanceNm);
    const y = yFromAlt(pt.altitudeFeet);

    ctx.fillStyle = pt.pointType === 'TOC' || pt.pointType === 'TOD' ? '#06b6d4' : '#f59e0b';
    ctx.beginPath();
    ctx.arc(x, y, 4.5, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#f8fafc';
    ctx.font = 'bold 10px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(pt.identifier, x, y - 10);
    ctx.font = '9px monospace';
    ctx.fillStyle = '#94a3b8';
    ctx.fillText(`FL${pt.flightLevel}`, x, y + 16);
  });

  // Summary tag
  document.getElementById('profileSummary').textContent = 
    `Dist: ${calc.totalDistanceNm} NM | ETE: ${calc.totalFlightTimeMinutes} min | Cruise: FL${calc.topOfClimb.flightLevel}`;
}

// --- 4D Points Table ---
function renderPointsTable(points) {
  const tbody = document.getElementById('pointsTableBody');
  tbody.innerHTML = '';

  for (const pt of points) {
    let typeLabel = `<strong>${pt.pointType}</strong>`;
    if (pt.pointType === 'INITIAL_CLIMB') {
      typeLabel = `<strong style="color: #22c55e;">INITIAL_CLIMB (5 NM)</strong>`;
    } else if (pt.pointType === 'APPROACH_INTERCEPT') {
      typeLabel = `<strong style="color: #eab308;">APPROACH_INTERCEPT (17 NM ILS)</strong>`;
    }

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${typeLabel}</td>
      <td><strong>${pt.identifier}</strong></td>
      <td>FL${pt.flightLevel}</td>
      <td>${pt.altitudeFeet.toLocaleString()} ft</td>
      <td>${pt.cumulativeDistanceNm} NM</td>
      <td>${pt.groundSpeedKnots} kt</td>
      <td>${pt.estimatedTimestamp.substring(11, 19)} UTC</td>
      <td>${pt.associatedAirspace || '-'}</td>
    `;
    tbody.appendChild(tr);
  }
}

// --- FIXM Payload Generator ---
function buildCurrentPlanObject(calcRes) {
  const calc = calcRes.calculated;
  const dep = calcRes.departureAirport;
  const arr = calcRes.arrivalAirport;
  const acType = document.getElementById('aircraftType').value;
  const ac = gAircraft.find(a => a.icaoType === acType) || {};
  const eobt = document.getElementById('eobt').value;

  gCurrentPlan = {
    gufi: '00000000-0000-0000-0000-000000000000', // assigned on filing
    status: 'PLANNED',
    messageType: 'PRELIMINARY',
    filingTime: new Date().toISOString(),
    flightIdentification: {
      aircraftIdentification: document.getElementById('callsign').value || 'EIN157',
      aircraftRegistration: document.getElementById('registration').value || 'EI-DVM'
    },
    aircraft: {
      aircraftType: acType,
      wakeTurbulence: ac.wakeTurbulenceCategory || 'M',
      capabilities: {
        standardEquipment: document.getElementById('equipment').value || 'SDFGIRW/LB1',
        navigation: ['RNAV 1', 'RNAV 5', 'RNP 4'],
        communication: ['VHF 8.33 kHz', 'CPDLC'],
        surveillance: ['ADS-B Out', 'Mode S Transponder']
      }
    },
    departure: {
      aerodrome: dep.icao,
      runway: document.getElementById('depRunway').value || undefined,
      elevationFeet: dep.elevationFeet,
      estimatedOffBlockTime: eobt ? new Date(eobt).toISOString() : new Date().toISOString()
    },
    arrival: {
      aerodrome: arr.icao,
      runway: document.getElementById('arrRunway').value || undefined,
      elevationFeet: arr.elevationFeet,
      estimatedTimeOfArrival: calc.points[calc.points.length - 1].estimatedTimestamp
    },
    enRoute: {
      cruisingLevel: `F${calc.topOfClimb.flightLevel}`,
      cruisingSpeed: `N0${ac.cruiseTasKnots || 450}`,
      routeString: `${dep.icao} ${gSelectedWaypoints.join(' ')} ${arr.icao}`,
      airspaceCrossings: calc.firCrossings
    },
    trajectory: {
      points4D: calc.points,
      topOfClimb: calc.topOfClimb,
      topOfDescent: calc.topOfDescent,
      totalDistanceNm: calc.totalDistanceNm,
      totalFlightTimeMinutes: calc.totalFlightTimeMinutes
    },
    remarks: 'SWIM FF-ICE DEMO'
  };
}

function updateFixmDisplay(type) {
  const pre = document.getElementById('fixmOutput');
  if (type === 'JSON') {
    pre.textContent = JSON.stringify(gCurrentPlan || {}, null, 2);
  } else {
    pre.textContent = getFixmXmlString();
  }
}

function getFixmXmlString() {
  if (!gCurrentPlan) return '<!-- No flight plan generated yet -->';
  const p = gCurrentPlan;

  const pointsXml = (p.trajectory.points4D || []).map(pt => `        <fx:point4D>
          <fx:pointType>${pt.pointType}</fx:pointType>
          <fx:pointIdentifier>${pt.identifier}</fx:pointIdentifier>
          <fx:position>
            <fb:pos>${pt.coordinates.latitude.toFixed(6)} ${pt.coordinates.longitude.toFixed(6)}</fb:pos>
          </fx:position>
          <fx:level>
            <fb:altitude uom="FT">${pt.altitudeFeet}</fb:altitude>
            <fb:flightLevel>F${String(pt.flightLevel).padStart(3, '0')}</fb:flightLevel>
          </fx:level>
          <fx:time>
            <fb:estimatedTime>${pt.estimatedTimestamp}</fb:estimatedTime>
            <fb:elapsedSeconds>${pt.cumulativeTimeSeconds}</fb:elapsedSeconds>
          </fx:time>
          <fx:cumulativeDistance uom="NM">${pt.cumulativeDistanceNm}</fx:cumulativeDistance>
          ${pt.associatedAirspace ? `<fx:airspace>${pt.associatedAirspace}</fx:airspace>` : ''}
        </fx:point4D>`).join('\n');

  return `<?xml version="1.0" encoding="UTF-8"?>
<fx:Flight xmlns:fx="http://www.fixm.aero/flight/4.2"
           xmlns:fb="http://www.fixm.aero/base/4.2"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <fx:gufi codeSpace="urn:uuid">urn:uuid:${p.gufi}</fx:gufi>
  <fx:flightStatus>${p.status}</fx:flightStatus>
  <fx:messageType>${p.messageType}</fx:messageType>
  <fx:filingTime>${p.filingTime}</fx:filingTime>
  <fx:flightIdentification>
    <fx:aircraftIdentification>${p.flightIdentification.aircraftIdentification}</fx:aircraftIdentification>
  </fx:flightIdentification>
  <fx:aircraft>
    <fx:aircraftType>${p.aircraft.aircraftType}</fx:aircraftType>
    <fx:wakeTurbulenceCategory>${p.aircraft.wakeTurbulence}</fx:wakeTurbulenceCategory>
    <fx:capabilities>
      <fx:standardEquipment>${p.aircraft.capabilities.standardEquipment}</fx:standardEquipment>
    </fx:capabilities>
  </fx:aircraft>
  <fx:departure>
    <fx:aerodrome>${p.departure.aerodrome}</fx:aerodrome>
    <fx:estimatedOffBlockTime>${p.departure.estimatedOffBlockTime}</fx:estimatedOffBlockTime>
  </fx:departure>
  <fx:arrival>
    <fx:aerodrome>${p.arrival.aerodrome}</fx:aerodrome>
    <fx:estimatedTimeOfArrival>${p.arrival.estimatedTimeOfArrival}</fx:estimatedTimeOfArrival>
  </fx:arrival>
  <fx:routeTrajectory>
    <fx:trajectoryProfile>
      <fx:totalDistance uom="NM">${p.trajectory.totalDistanceNm}</fx:totalDistance>
      <fx:totalFlightTimeMinutes>${p.trajectory.totalFlightTimeMinutes}</fx:totalFlightTimeMinutes>
      <fx:agreedTrajectory>
${pointsXml}
      </fx:agreedTrajectory>
    </fx:trajectoryProfile>
  </fx:routeTrajectory>
</fx:Flight>`;
}

// --- Modal Management & Explainer Tooltips ---
function setupModals() {
  // Generic modal openers
  document.getElementById('btnOpenAbout').addEventListener('click', () => openModal('aboutModal'));
  document.getElementById('btnOpenTrafficGen').addEventListener('click', () => openModal('trafficModal'));
  document.getElementById('btnOpenCapsModal').addEventListener('click', () => openModal('capabilitiesModal'));
  document.getElementById('btnOpenWaypointMap').addEventListener('click', openWaypointMapModal);

  // Close buttons
  document.querySelectorAll('[data-close]').forEach(btn => {
    btn.addEventListener('click', () => {
      const modalId = btn.getAttribute('data-close');
      closeModal(modalId);
    });
  });

  // Banner dismiss buttons
  document.querySelectorAll('[data-dismiss]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const bannerId = btn.getAttribute('data-dismiss');
      const b = document.getElementById(bannerId);
      if (b) b.classList.add('hidden');
    });
  });

  // Close on clicking backdrop outside dialog
  document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
    backdrop.addEventListener('click', e => {
      if (e.target === backdrop) backdrop.classList.add('hidden');
    });
  });

  // Contextual "?" Explainer Buttons
  const infoDictionary = {
    callsign: {
      title: "Aircraft Identification (Callsign)",
      body: `<p>In FF-ICE and ICAO Doc 4444, the aircraft identification is the operational telephony designator of the aircraft operator followed by the flight number (e.g. <strong>EIN157</strong> for Aer Lingus 157, <strong>BAW826</strong> for British Airways 826).</p>
      <p style="margin-top: 8px;">It must match the callsign used for radiotelephony communications with Air Traffic Control.</p>`
    },
    eobt: {
      title: "Estimated Off-Block Time (EOBT) vs Take-Off Time (ETOT)",
      body: `<p><strong>EOBT (Estimated Off-Block Time):</strong> The scheduled time at which the aircraft will commence movement/pushback from the parking stand.</p>
      <p style="margin-top: 8px;"><strong>ETOT (Estimated Take-Off Time):</strong> The actual wheels-off time at the departure runway threshold. Runway slotting, wake vortex decay, and airborne 4D deconfliction apply strictly at ETOT.</p>
      <p style="margin-top: 8px;"><strong>Derivation:</strong> <code>EOBT = ETOT - EXOT</code> (where EXOT is Estimated Taxi-Out Time for the aerodrome, e.g. 20 min for EGLL, 15 min for EIDW).</p>
      <p style="margin-top: 8px;"><strong>Arrival:</strong> Touchdown occurs at <strong>ELDT</strong> (Estimated Landing Time), and gate in-block arrival occurs at <code>EIBT = ELDT + EXIT</code>.</p>`
    },
    airports: {
      title: "Aerodromes & Runways (UK & Ireland)",
      body: `<p>Aerodromes are defined using 4-letter ICAO location indicators (e.g. <strong>EGLL</strong> for London Heathrow, <strong>EIDW</strong> for Dublin International).</p>
      <p style="margin-top: 8px;">Runway designator, dimensions, and true bearing are extracted directly from official UK and Irish Aeronautical Information Publications (AIP).</p>`
    },
    equipment: {
      title: "Aircraft Equipment & Capabilities",
      body: `<p>Defines the aircraft's avionics, navigation, communication, and surveillance equipment complying with ICAO Annex 2/11 and FF-ICE FIXM specifications.</p>
      <p style="margin-top: 8px;">Click <strong>'⚙️ Configure Capabilities'</strong> to open the interactive checkbox builder with full explainers for RNAV 1, B-RNAV, RNP 4, 8.33 kHz, CPDLC, and ADS-B.</p>`
    },
    aircraft: {
      title: "Aircraft Performance & Aerodynamics",
      body: `<p>Aerodynamic performance specifications determine vertical climb/descent profiles, fuel burn, and achievable cruising levels under ICAO Doc 9965 & Annex 6:</p>
      <ul style="padding-left: 20px; margin-top: 8px;">
        <li><strong>Service Ceiling:</strong> Maximum certified pressure altitude for the aircraft type.</li>
        <li><strong>Average Climb Rate:</strong> Nominal vertical velocity (fpm) to Top of Climb (TOC).</li>
        <li><strong>Cruise True Airspeed (TAS):</strong> Cruising ground/calibrated speed in knots.</li>
        <li><strong>Average Descent Rate:</strong> Vertical descent velocity (fpm) from Top of Descent (TOD).</li>
      </ul>
      <p style="margin-top: 8px;">Performance profiles are loaded dynamically from <code>config/aircraft_performance.json</code> with custom dispatcher overrides and live hot-reloading.</p>`
    },
    flightlevel: {
      title: "Cruising Level & Semicircular Rule",
      body: `<p>Flight levels are pressure altitudes based on standard altimeter setting (1013.25 hPa / 29.92 inHg), expressed in hundreds of feet (e.g. <strong>FL280 = 28,000 ft</strong>).</p>
      <p style="margin-top: 8px;"><strong>ICAO Semicircular Cruising Levels:</strong></p>
      <ul style="padding-left: 20px; margin-top: 4px;">
        <li><strong>Eastbound (Magnetic Track 000° to 179°):</strong> ODD Flight Levels (FL250, FL270, FL290, FL310, FL330, FL350, FL370, FL390).</li>
        <li><strong>Westbound (Magnetic Track 180° to 359°):</strong> EVEN Flight Levels (FL260, FL280, FL300, FL320, FL340, FL360, FL380, FL400).</li>
      </ul>`
    }
  };

  document.querySelectorAll('.info-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const infoKey = btn.getAttribute('data-info');
      const data = infoDictionary[infoKey];
      if (data) {
        document.getElementById('infoModalTitle').textContent = `❓ ${data.title}`;
        document.getElementById('infoModalBody').innerHTML = data.body;
        openModal('infoModal');
      }
    });
  });

  // Apply Capabilities Button in Modal
  document.getElementById('btnApplyCapabilities').addEventListener('click', applySelectedCapabilities);

  // Traffic Generator Button
  document.getElementById('btnExecuteTrafficGen').addEventListener('click', executeTrafficGeneration);
}

function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.remove('hidden');
}

function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.add('hidden');
}

function applySelectedCapabilities() {
  const standardCodes = ['S']; // Standard VOR/ILS/VHF
  const navCaps = [];
  const comCaps = [];
  const surCaps = [];

  if (document.getElementById('cap_rnav1').checked) { navCaps.push('RNAV 1'); standardCodes.push('R'); }
  if (document.getElementById('cap_rnav5').checked) { navCaps.push('RNAV 5'); standardCodes.push('R'); }
  if (document.getElementById('cap_rnp4').checked) { navCaps.push('RNP 4'); standardCodes.push('R'); }
  if (document.getElementById('cap_ils').checked) { navCaps.push('ILS'); standardCodes.push('I'); }
  if (document.getElementById('cap_vor').checked) { navCaps.push('VOR/DME'); standardCodes.push('O', 'D'); }
  if (document.getElementById('cap_gnss').checked) { navCaps.push('GNSS'); standardCodes.push('G'); }

  if (document.getElementById('cap_833').checked) { comCaps.push('VHF 8.33 kHz'); standardCodes.push('Y'); }
  if (document.getElementById('cap_cpdlc').checked) { comCaps.push('CPDLC ATN-B1'); standardCodes.push('J1'); }
  if (document.getElementById('cap_hf').checked) { comCaps.push('HF RTF'); standardCodes.push('H'); }
  if (document.getElementById('cap_satcom').checked) { comCaps.push('SATCOM'); standardCodes.push('M1'); }

  let surCode = 'S';
  if (document.getElementById('cap_modes').checked) { surCaps.push('Mode S EHS'); surCode = 'L'; }
  if (document.getElementById('cap_adsb_out').checked) { surCaps.push('ADS-B Out'); surCode = 'LB1'; }
  if (document.getElementById('cap_adsb_in').checked) { surCaps.push('ADS-B In'); }
  if (document.getElementById('cap_tcas').checked) { surCaps.push('TCAS II v7.1'); standardCodes.push('W'); }

  const uniqueCodes = Array.from(new Set(standardCodes)).sort().join('');
  const finalEquipmentString = `${uniqueCodes}/${surCode}`;

  document.getElementById('equipment').value = finalEquipmentString;
  closeModal('capabilitiesModal');

  // If plan exists, update it
  if (gCurrentPlan) {
    gCurrentPlan.aircraft.capabilities = {
      standardEquipment: finalEquipmentString,
      navigation: navCaps,
      communication: comCaps,
      surveillance: surCaps
    };
    updateFixmDisplay('XML');
  }

  alert(`Capabilities updated to: ${finalEquipmentString}`);
}

// --- Execute Traffic Generation ---
async function executeTrafficGeneration() {
  const count = parseInt(document.getElementById('trafficCount').value, 10) || 20;
  const hours = parseFloat(document.getElementById('trafficHours').value) || 6.0;
  const btn = document.getElementById('btnExecuteTrafficGen');

  btn.disabled = true;
  btn.textContent = '⏳ Generating Flights...';

  try {
    const res = await fetch(`/api/v1/traffic/generate?count=${count}&hours=${hours}`, { method: 'POST' }).then(r => r.json());
    alert(`🎉 Traffic Generation Complete!\n\n${res.message}`);
    closeModal('trafficModal');
    await refreshFiledPlans();
  } catch (err) {
    console.error('Traffic generation error:', err);
    alert('Failed to generate traffic.');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generate & Populate DB';
  }
}

// --- Dedicated 4D Conflict Tester ---
async function test4DConflicts() {
  if (!gCurrentTrajectory || !gCurrentTrajectory.points) {
    await calculateTrajectory();
    if (!gCurrentTrajectory) return;
  }

  try {
    const payload = {
      callsign: document.getElementById('callsign').value || 'TEST_FLIGHT',
      aircraftType: document.getElementById('aircraftType')?.value || 'A320',
      points4D: gCurrentTrajectory.points
    };

    const res = await fetch('/api/v1/trajectory/check-conflicts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(r => r.json());

    displayDeconflictionAdvisory(res);

    if (res.hasConflicts) {
      alert(`⚠️ 4D Separation Conflict Detected!\n\n${res.conflictCount} active flight(s) in the database violate separation criteria.\nSee the deconfliction panel for tactical resolutions.`);
    } else {
      alert(`🛡️ 4D Trajectory Deconflicted!\n\nNo conflicts found. All 5.0 NM horizontal, 1,000 ft vertical, and 5-minute temporal separation criteria satisfied.`);
    }
  } catch (err) {
    console.error('Conflict check error:', err);
    alert('Failed to check 4D airspace conflicts.');
  }
}

// --- File Plan via SWIM POST Service (with Strict Mode Support) ---
async function fileFlightPlan() {
  if (!gCurrentPlan) {
    alert('Please calculate a trajectory before filing.');
    return;
  }

  const isStrict = document.getElementById('chkStrictDeconfliction').checked;
  gCurrentPlan.strictDeconfliction = isStrict;

  try {
    const res = await fetch(`/api/v1/ffice/plans?strict_deconfliction=${isStrict}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(gCurrentPlan)
    });

    if (res.status === 409) {
      const errData = await res.json();
      const detail = errData.detail || {};
      alert(`🚫 FLIGHT PLAN REJECTED (Strict SWIM Enforcement):\n\n${detail.error || 'Separation conflict detected.'}\n\nConflicting flights: ${detail.conflictCount}\n\nResolutions:\n${(detail.resolutions || []).join('\n')}`);
      return;
    }

    if (!res.ok) {
      const errText = await res.text();
      alert(`Filing failed (${res.status}): ${errText}`);
      return;
    }

    const data = await res.json();
    gCurrentPlan = data.plan;

    if (data.deconfliction && data.deconfliction.hasConflicts) {
      alert(`⚠️ FF-ICE Flight Plan Filed in DB with Separation Warnings!\n\nAssigned GUFI: ${data.plan.gufi}\n\nNotice: ${data.deconfliction.conflictCount} strategic conflict(s) detected with other traffic.`);
    } else {
      alert(`✈️ FF-ICE Flight Plan Filed Successfully via SWIM!\n\nAssigned GUFI: ${data.plan.gufi}\nStatus: ${data.plan.status}\n4D Deconfliction: Clear (No traffic conflicts)`);
    }

    await refreshFiledPlans();
    updateFixmDisplay('XML');
  } catch (err) {
    console.error('Filing error:', err);
    alert('Failed to file plan with SWIM service.');
  }
}

async function refreshFiledPlans() {
  try {
    const chkShowAll = document.getElementById('chkShowAllPlans');
    const includeExpired = chkShowAll ? chkShowAll.checked : false;
    const url = `/api/v1/ffice/plans?active_only=${!includeExpired}&include_expired=${includeExpired}`;
    const plans = await fetch(url).then(r => r.json());
    gFiledPlans = plans;

    const summaryEl = document.getElementById('filedFilterSummary');
    if (summaryEl) {
      summaryEl.textContent = includeExpired ? 'All Plans (Including Completed / Expired)' : 'Upcoming & In-Flight Plans Only';
    }

    const filedCountEl = document.getElementById('filedCount');
    if (filedCountEl) filedCountEl.textContent = plans.length;
    const activeCountEl = document.getElementById('filedActiveCount');
    if (activeCountEl) {
      const activeCount = plans.filter(p => p.operationalStatus === 'UPCOMING' || p.operationalStatus === 'IN_FLIGHT').length;
      activeCountEl.textContent = activeCount;
    }

    const tbody = document.getElementById('filedTableBody');
    tbody.innerHTML = '';

    if (!plans || plans.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="text-center" style="padding: 24px; color: var(--text-muted);">No upcoming or in-flight flight plans found. Check "Show Completed / Expired Plans" to view historical logs.</td></tr>';
      return;
    }

    for (const p of plans) {
      const tr = document.createElement('tr');
      const opPhase = p.operationalStatus || (p.status === 'CANCELLED' ? 'CANCELLED' : 'ACTIVE');

      let badgeHtml = '';
      if (opPhase === 'UPCOMING') {
        badgeHtml = '<span class="swim-badge badge-upcoming">🟢 UPCOMING</span>';
      } else if (opPhase === 'IN_FLIGHT') {
        badgeHtml = '<span class="swim-badge badge-inflight">✈️ IN-FLIGHT</span>';
      } else if (opPhase === 'COMPLETED') {
        badgeHtml = '<span class="swim-badge badge-completed">🏁 COMPLETED</span>';
      } else if (opPhase === 'EXPIRED') {
        badgeHtml = '<span class="swim-badge badge-expired">⚠️ EXPIRED</span>';
      } else if (opPhase === 'CANCELLED') {
        badgeHtml = '<span class="swim-badge badge-cancelled">❌ CANCELLED</span>';
      } else {
        badgeHtml = `<span class="swim-badge">${opPhase}</span>`;
      }

      const eobtStr = p.departure?.estimatedOffBlockTime ? p.departure.estimatedOffBlockTime.substring(11, 16) + 'Z' : 'N/A';
      const etaStr = p.arrival?.estimatedTimeOfArrival ? p.arrival.estimatedTimeOfArrival.substring(11, 16) + 'Z' : 'N/A';
      const canCancel = (p.status !== 'CANCELLED' && opPhase !== 'COMPLETED' && opPhase !== 'EXPIRED');

      tr.innerHTML = `
        <td><code title="${p.gufi}">${p.gufi.substring(0, 8)}...</code></td>
        <td>${badgeHtml}</td>
        <td><span class="swim-badge" style="font-size: 0.72rem;">${p.status}</span></td>
        <td><strong>${p.flightIdentification?.aircraftIdentification || 'N/A'}</strong> <span style="font-size:0.75rem; color:var(--text-muted)">(${p.aircraft?.aircraftType || ''})</span></td>
        <td>${p.departure?.aerodrome || ''} &rarr; ${p.arrival?.aerodrome || ''}</td>
        <td>${eobtStr}</td>
        <td>${etaStr}</td>
        <td>${p.enRoute?.cruisingLevel || ''}</td>
        <td>
          ${canCancel ? `<button class="btn-link" onclick="cancelFiledPlan('${p.gufi}')" style="color:var(--accent-red,#ef4444); cursor:pointer;">Cancel</button>` : '<span style="color:var(--text-muted); font-size:0.8rem;">Archived</span>'}
        </td>
      `;
      tbody.appendChild(tr);
    }
  } catch (err) {
    console.error('Failed to refresh filed plans:', err);
  }
}

async function sweepStalePlansNow() {
  try {
    const btn = document.getElementById('btnSweepStalePlans');
    if (btn) btn.disabled = true;
    const res = await fetch('/api/v1/ffice/plans/sweep', { method: 'POST' }).then(r => r.json());
    alert(`🧹 Background Lifecycle Audit Finished!\n\n${res.message}`);
    await refreshFiledPlans();
  } catch (err) {
    alert(`Failed to run background sweep: ${err.message}`);
  } finally {
    const btn = document.getElementById('btnSweepStalePlans');
    if (btn) btn.disabled = false;
  }
}


window.cancelFiledPlan = async function(gufi) {
  if (!confirm(`Are you sure you want to cancel plan ${gufi}?`)) return;
  try {
    await fetch(`/api/v1/ffice/plans/${gufi}`, { method: 'DELETE' });
    alert('Flight plan marked CANCELLED.');
    await refreshFiledPlans();
  } catch (err) {
    console.error(err);
  }
};

function downloadFile(filename, text, mimeType) {
  const blob = new Blob([text], { type: mimeType });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

// --- Interactive Map Waypoint Selector Modal ---
function initWaypointMapModal() {
  document.getElementById('mapWaypointFilter').addEventListener('input', e => {
    filterModalWaypoints(e.target.value);
  });

  document.getElementById('btnClearMapRoute').addEventListener('click', () => {
    gModalWaypoints = [];
    document.getElementById('autofillNotice').classList.add('hidden');
    updateModalRouteDisplay();
    refreshAllModalPopups();
  });

  document.getElementById('btnAutoFillRoute').addEventListener('click', autoFillModalRoute);

  document.getElementById('btnApplyMapRoute').addEventListener('click', () => {
    gSelectedWaypoints = [...gModalWaypoints];
    renderWaypointChips();
    closeModal('waypointMapModal');
    calculateTrajectory();
  });
}

async function autoFillModalRoute() {
  const depIcao = document.getElementById('depAirport').value;
  const arrIcao = document.getElementById('arrAirport').value;
  const btn = document.getElementById('btnAutoFillRoute');
  const notice = document.getElementById('autofillNotice');

  if (!depIcao || !arrIcao) {
    alert('Please select departure and arrival aerodromes first.');
    return;
  }

  btn.disabled = true;
  btn.textContent = '⏳ Auto-Filling Gaps...';

  try {
    const payload = {
      departureIcao: depIcao,
      arrivalIcao: arrIcao,
      waypoints: gModalWaypoints
    };

    const res = await fetch('/api/v1/route/autofill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(r => r.json());

    gModalWaypoints = res.filledWaypoints || [];
    updateModalRouteDisplay();
    refreshAllModalPopups();

    notice.classList.remove('hidden');
    if (res.insertedCount > 0) {
      notice.innerHTML = `
        <span>✨ <strong>Auto-Fill Complete:</strong> Added <strong>${res.insertedCount}</strong> intermediate fix${res.insertedCount > 1 ? 'es' : ''} (${res.insertedWaypoints.join(', ')}) ${res.airwaysUsed.length > 0 ? `via ATS Airway(s) ${res.airwaysUsed.join(', ')}` : 'along optimal corridor'}.</span>
        <button type="button" class="btn-link" onclick="document.getElementById('autofillNotice').classList.add('hidden')">&times;</button>
      `;
    } else {
      notice.innerHTML = `
        <span>✅ <strong>Route is Complete:</strong> All ATS corridors and spacing intervals are satisfied.</span>
        <button type="button" class="btn-link" onclick="document.getElementById('autofillNotice').classList.add('hidden')">&times;</button>
      `;
    }
  } catch (err) {
    console.error('Auto-fill error:', err);
    alert('Failed to auto-fill route waypoints.');
  } finally {
    btn.disabled = false;
    btn.textContent = '✨ Auto-Fill Route / Airway Gaps';
  }
}

async function openWaypointMapModal() {
  openModal('waypointMapModal');
  gModalWaypoints = [...gSelectedWaypoints];
  document.getElementById('autofillNotice').classList.add('hidden');

  if (!gWaypointSelectorMap) {
    gWaypointSelectorMap = L.map('waypointSelectorMap').setView([53.8, -4.5], 6);

    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 18
    }).addTo(gWaypointSelectorMap);

    gModalAirportsLayer = L.layerGroup().addTo(gWaypointSelectorMap);
    gModalRouteLayer = L.layerGroup().addTo(gWaypointSelectorMap);
    gModalWptLayer = L.layerGroup().addTo(gWaypointSelectorMap);

    initWaypointMapModal();
  }

  setTimeout(() => {
    gWaypointSelectorMap.invalidateSize();
  }, 150);

  if (gAllWaypointsCache.length === 0) {
    document.getElementById('mapWaypointCount').textContent = 'Loading aeronautical fixes...';
    try {
      const wps = await fetch('/api/v1/waypoints?limit=1500').then(r => r.json());
      gAllWaypointsCache = wps || [];
    } catch (e) {
      console.error(e);
      gAllWaypointsCache = [];
    }
  }

  renderWaypointMapMarkers();
  updateModalRouteDisplay();
}

function renderWaypointMapMarkers() {
  gModalAirportsLayer.clearLayers();
  gModalWptLayer.clearLayers();
  gModalMarkersMap = {};

  const depIcao = document.getElementById('depAirport').value;
  const arrIcao = document.getElementById('arrAirport').value;
  const dep = gAirports.find(a => a.icao === depIcao);
  const arr = gAirports.find(a => a.icao === arrIcao);

  // Plot Dep & Arr airports
  if (dep) {
    const depMarker = L.circleMarker([dep.latitude, dep.longitude], {
      color: '#10b981',
      fillColor: '#10b981',
      fillOpacity: 0.9,
      radius: 9,
      weight: 2
    }).addTo(gModalAirportsLayer);
    depMarker.bindTooltip(`Departure: ${dep.icao}`, { permanent: false, direction: 'top' });
  }

  if (arr) {
    const arrMarker = L.circleMarker([arr.latitude, arr.longitude], {
      color: '#06b6d4',
      fillColor: '#06b6d4',
      fillOpacity: 0.9,
      radius: 9,
      weight: 2
    }).addTo(gModalAirportsLayer);
    arrMarker.bindTooltip(`Arrival: ${arr.icao}`, { permanent: false, direction: 'top' });
  }

  // Plot All Waypoints
  document.getElementById('mapWaypointCount').textContent = `Plotted: ${gAllWaypointsCache.length} UK & Irish aeronautical fixes`;

  for (const w of gAllWaypointsCache) {
    const isSelected = gModalWaypoints.includes(w.name);
    const marker = L.circleMarker([w.latitude, w.longitude], {
      color: isSelected ? '#f59e0b' : '#38bdf8',
      fillColor: isSelected ? '#d97706' : '#0284c7',
      fillOpacity: isSelected ? 0.95 : 0.75,
      radius: isSelected ? 6 : 4,
      weight: isSelected ? 2 : 1
    }).addTo(gModalWptLayer);

    marker.bindTooltip(w.name, { permanent: false, direction: 'top' });
    marker.on('click', () => {
      marker.bindPopup(buildWaypointPopupHtml(w)).openPopup();
    });

    gModalMarkersMap[w.name] = { marker, data: w };
  }
}

function buildWaypointPopupHtml(w) {
  const idx = gModalWaypoints.indexOf(w.name);
  const isSelected = idx !== -1;
  const stepNum = isSelected ? idx + 1 : gModalWaypoints.length + 1;

  return `
    <div class="wpt-popup-content">
      <strong>${w.name}</strong> (${w.country || 'Aeronautical Fix'})<br>
      <span style="font-size: 11px; color: #475569;">Lat: ${w.latitude.toFixed(4)}, Lon: ${w.longitude.toFixed(4)}</span>
      <div class="wpt-popup-btns">
        ${isSelected
          ? `<button type="button" class="wpt-popup-btn danger" onclick="removeModalWaypoint('${w.name}')">❌ Remove (#${stepNum})</button>
             ${idx > 0 ? `<button type="button" class="wpt-popup-btn" onclick="moveModalWaypoint('${w.name}', -1)">⬆️ Earlier</button>` : ''}
             ${idx < gModalWaypoints.length - 1 ? `<button type="button" class="wpt-popup-btn" onclick="moveModalWaypoint('${w.name}', 1)">⬇️ Later</button>` : ''}`
          : `<button type="button" class="wpt-popup-btn" onclick="addModalWaypoint('${w.name}')">➕ Append to Sequence (#${stepNum})</button>`
        }
      </div>
    </div>
  `;
}

window.addModalWaypoint = function(name) {
  if (!gModalWaypoints.includes(name)) {
    gModalWaypoints.push(name);
  }
  updateModalRouteDisplay();
  refreshAllModalPopups();
};

window.removeModalWaypoint = function(name) {
  gModalWaypoints = gModalWaypoints.filter(w => w !== name);
  updateModalRouteDisplay();
  refreshAllModalPopups();
};

window.moveModalWaypoint = function(name, dir) {
  const idx = gModalWaypoints.indexOf(name);
  if (idx === -1) return;
  const target = idx + dir;
  if (target < 0 || target >= gModalWaypoints.length) return;
  const temp = gModalWaypoints[idx];
  gModalWaypoints[idx] = gModalWaypoints[target];
  gModalWaypoints[target] = temp;
  updateModalRouteDisplay();
  refreshAllModalPopups();
};

function refreshAllModalPopups() {
  for (const name in gModalMarkersMap) {
    const item = gModalMarkersMap[name];
    const isSelected = gModalWaypoints.includes(name);

    item.marker.setStyle({
      color: isSelected ? '#f59e0b' : '#38bdf8',
      fillColor: isSelected ? '#d97706' : '#0284c7',
      fillOpacity: isSelected ? 0.95 : 0.75,
      radius: isSelected ? 6 : 4,
      weight: isSelected ? 2 : 1
    });

    if (item.marker.isPopupOpen()) {
      item.marker.setPopupContent(buildWaypointPopupHtml(item.data));
    }
  }
}

function updateModalRouteDisplay() {
  gModalRouteLayer.clearLayers();

  const depIcao = document.getElementById('depAirport').value;
  const arrIcao = document.getElementById('arrAirport').value;
  const depRwy = document.getElementById('depRunway').value || 'ACTIVE';
  const arrRwy = document.getElementById('arrRunway').value || 'ACTIVE';

  const dep = gAirports.find(a => a.icao === depIcao);
  const arr = gAirports.find(a => a.icao === arrIcao);

  const chipsContainer = document.getElementById('mapModalChips');
  chipsContainer.innerHTML = '';

  const pts = [];
  if (dep) {
    pts.push([dep.latitude, dep.longitude]);
    const depChip = document.createElement('span');
    depChip.className = 'waypoint-chip rwy-fix';
    depChip.innerHTML = `🛫 <strong>${dep.icao} (RWY ${depRwy})</strong>`;
    chipsContainer.appendChild(depChip);

    // Initial 5 NM straight climbout corridor label
    const climbChip = document.createElement('span');
    climbChip.className = 'waypoint-chip rwy-fix';
    climbChip.innerHTML = `<span>5 NM Climb-Out</span>`;
    chipsContainer.appendChild(climbChip);
  }

  gModalWaypoints.forEach((wName, i) => {
    const wObj = gAllWaypointsCache.find(x => x.name === wName) || gWaypoints.find(x => x.name === wName);
    if (wObj) {
      pts.push([wObj.latitude, wObj.longitude]);
    }
    const chip = document.createElement('span');
    chip.className = 'waypoint-chip draggable-chip';
    chip.draggable = true;
    chip.dataset.index = i;
    chip.title = 'Drag to reorder waypoint sequence';
    chip.innerHTML = `
      <span class="drag-grip" title="Drag to reorder">⋮⋮</span>
      <span class="sequence-step-num">${i + 1}</span>
      <span>${wName}</span>
      <span class="chip-remove" onclick="removeModalWaypoint('${wName}')" title="Remove">&times;</span>
    `;

    chip.addEventListener('dragstart', e => {
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', i.toString());
      chip.classList.add('dragging');
    });

    chip.addEventListener('dragend', () => {
      chip.classList.remove('dragging');
      chipsContainer.querySelectorAll('.draggable-chip').forEach(c => c.classList.remove('drag-over-left', 'drag-over-right'));
    });

    chip.addEventListener('dragover', e => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      const rect = chip.getBoundingClientRect();
      const midX = rect.left + rect.width / 2;
      if (e.clientX < midX) {
        chip.classList.add('drag-over-left');
        chip.classList.remove('drag-over-right');
      } else {
        chip.classList.add('drag-over-right');
        chip.classList.remove('drag-over-left');
      }
    });

    chip.addEventListener('dragleave', () => {
      chip.classList.remove('drag-over-left', 'drag-over-right');
    });

    chip.addEventListener('drop', e => {
      e.preventDefault();
      chip.classList.remove('drag-over-left', 'drag-over-right');
      const fromIdx = parseInt(e.dataTransfer.getData('text/plain'), 10);
      if (isNaN(fromIdx) || fromIdx === i) return;

      const rect = chip.getBoundingClientRect();
      const midX = rect.left + rect.width / 2;
      let toIdx = e.clientX < midX ? i : i + 1;
      if (fromIdx < toIdx) toIdx--;

      const moved = gModalWaypoints.splice(fromIdx, 1)[0];
      gModalWaypoints.splice(toIdx, 0, moved);
      updateModalRouteDisplay();
      refreshAllModalPopups();
    });

    chipsContainer.appendChild(chip);
  });

  if (arr) {
    const ilsChip = document.createElement('span');
    ilsChip.className = 'waypoint-chip rwy-fix';
    ilsChip.innerHTML = `<span>17 NM ILS Intercept</span>`;
    chipsContainer.appendChild(ilsChip);

    pts.push([arr.latitude, arr.longitude]);
    const arrChip = document.createElement('span');
    arrChip.className = 'waypoint-chip rwy-fix';
    arrChip.innerHTML = `🛬 <strong>${arr.icao} (RWY ${arrRwy})</strong>`;
    chipsContainer.appendChild(arrChip);
  }

  if (pts.length >= 2) {
    const poly = L.polyline(pts, {
      color: '#f59e0b',
      weight: 3.5,
      opacity: 0.9,
      dashArray: '4, 4'
    }).addTo(gModalRouteLayer);

    gWaypointSelectorMap.fitBounds(poly.getBounds().pad(0.15));
  }
}

function filterModalWaypoints(query) {
  const q = (query || '').trim().toUpperCase();
  let count = 0;
  for (const name in gModalMarkersMap) {
    const item = gModalMarkersMap[name];
    if (!q || name.includes(q)) {
      if (!gModalWptLayer.hasLayer(item.marker)) {
        gModalWptLayer.addLayer(item.marker);
      }
      count++;
    } else {
      if (gModalWptLayer.hasLayer(item.marker)) {
        gModalWptLayer.removeLayer(item.marker);
      }
    }
  }
  document.getElementById('mapWaypointCount').textContent = `Showing ${count} matching aeronautical fixes`;
}

// ========================================================
// Conflicting Paths Map Visualizer (#conflictsMapModal)
// ========================================================
function openConflictsMapModal() {
  const modal = document.getElementById('conflictsMapModal');
  if (!modal) return;
  modal.classList.remove('hidden');

  if (!gConflictsMap) {
    gConflictsMap = L.map('conflictsMap').setView([53.8, -4.5], 6);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(gConflictsMap);
    gConflictsLayers = L.layerGroup().addTo(gConflictsMap);
  } else {
    gConflictsLayers.clearLayers();
  }

  setTimeout(() => {
    gConflictsMap.invalidateSize();
    renderConflictsMapContent();
  }, 150);
}

function renderConflictsMapContent() {
  if (!gConflictsMap || !gConflictsLayers) return;
  gConflictsLayers.clearLayers();

  const bounds = [];
  const candidateCallsign = document.getElementById('callsign').value || 'CANDIDATE';
  const candidateFl = document.getElementById('cruiseFl').value || '280';
  const candLabel = document.getElementById('legendCandidateLabel');
  if (candLabel) candLabel.textContent = `Candidate: ${candidateCallsign} (FL${candidateFl})`;

  // 1. Draw Candidate Flight Trajectory (Thick Gold/Amber Polyline)
  if (gCurrentTrajectory && gCurrentTrajectory.points && gCurrentTrajectory.points.length > 0) {
    const candLatLngs = gCurrentTrajectory.points.map(p => [p.coordinates.latitude, p.coordinates.longitude]);
    candLatLngs.forEach(ll => bounds.push(ll));

    L.polyline(candLatLngs, {
      color: '#f59e0b',
      weight: 4.5,
      opacity: 0.95
    }).addTo(gConflictsLayers);

    const pStart = gCurrentTrajectory.points[0];
    const pEnd = gCurrentTrajectory.points[gCurrentTrajectory.points.length - 1];

    L.circleMarker([pStart.coordinates.latitude, pStart.coordinates.longitude], {
      radius: 6,
      fillColor: '#f59e0b',
      color: '#ffffff',
      weight: 2,
      fillOpacity: 1.0
    }).bindTooltip(`🛫 ${candidateCallsign} Departure: ${pStart.identifier}`).addTo(gConflictsLayers);

    L.circleMarker([pEnd.coordinates.latitude, pEnd.coordinates.longitude], {
      radius: 6,
      fillColor: '#f59e0b',
      color: '#ffffff',
      weight: 2,
      fillOpacity: 1.0
    }).bindTooltip(`🛬 ${candidateCallsign} Arrival: ${pEnd.identifier}`).addTo(gConflictsLayers);
  }

  // 2. Draw Conflicting Flights Trajectories & Markers
  const TRAFFIC_COLORS = ['#ef4444', '#a855f7', '#06b6d4', '#f97316', '#ec4899', '#10b981'];
  const legendGroup = document.getElementById('legendTrafficGroup');
  const focusBar = document.getElementById('conflictsFocusBar');
  if (legendGroup) legendGroup.innerHTML = '';
  if (focusBar) focusBar.innerHTML = '';

  if (gCurrentDeconfliction && gCurrentDeconfliction.conflicts) {
    gCurrentDeconfliction.conflicts.forEach((conf, idx) => {
      const color = TRAFFIC_COLORS[idx % TRAFFIC_COLORS.length];

      // Legend entry
      if (legendGroup) {
        const chip = document.createElement('div');
        chip.className = 'legend-chip';
        chip.innerHTML = `
          <span class="legend-color-dot" style="background: ${color};"></span>
          <span>${conf.conflictingCallsign}</span>
        `;
        legendGroup.appendChild(chip);
      }

      // Draw full conflicting 4D trajectory if attached
      if (conf.conflictingTrajectory && conf.conflictingTrajectory.length > 0) {
        const trafficLatLngs = conf.conflictingTrajectory.map(p => [p.latitude, p.longitude]);
        trafficLatLngs.forEach(ll => bounds.push(ll));

        L.polyline(trafficLatLngs, {
          color: color,
          weight: 3.5,
          opacity: 0.85,
          dashArray: '5, 5'
        }).addTo(gConflictsLayers);

        const startPt = conf.conflictingTrajectory[0];
        const endPt = conf.conflictingTrajectory[conf.conflictingTrajectory.length - 1];

        L.circleMarker([startPt.latitude, startPt.longitude], {
          radius: 5,
          fillColor: color,
          color: '#ffffff',
          weight: 1.5,
          fillOpacity: 0.9
        }).bindTooltip(`${conf.conflictingCallsign} Dep: ${startPt.identifier}`).addTo(gConflictsLayers);

        L.circleMarker([endPt.latitude, endPt.longitude], {
          radius: 5,
          fillColor: color,
          color: '#ffffff',
          weight: 1.5,
          fillOpacity: 0.9
        }).bindTooltip(`${conf.conflictingCallsign} Arr: ${endPt.identifier}`).addTo(gConflictsLayers);
      }

      // 3. Place CPA Loss of Separation Marker
      bounds.push([conf.latitude, conf.longitude]);

      const pulseIcon = L.divIcon({
        className: 'cpa-pulse-container',
        html: '<div class="cpa-pulse-dot"></div>',
        iconSize: [20, 20],
        iconAnchor: [10, 10]
      });

      const cpaMarker = L.marker([conf.latitude, conf.longitude], { icon: pulseIcon }).addTo(gConflictsLayers);
      const cpaPopupContent = `
        <div style="font-family: inherit; font-size: 0.8rem; line-height: 1.4; min-width: 210px;">
          <div style="font-weight: 800; color: #ef4444; margin-bottom: 4px; display: flex; align-items: center; gap: 4px;">
            ⚠️ LOSS OF SEPARATION (CPA)
          </div>
          <div><strong>Candidate:</strong> ${candidateCallsign}</div>
          <div><strong>Conflicting Flight:</strong> ${conf.conflictingCallsign}</div>
          <div><strong>Location / Fix:</strong> ${conf.pointName || 'Enroute'}</div>
          <div><strong>Predicted CPA Time:</strong> ${conf.timeOfClosestApproach.substring(11, 19)} UTC</div>
          <div style="margin-top: 5px; padding-top: 5px; border-top: 1px solid rgba(255,255,255,0.15);">
            <div><strong>Horizontal Sep:</strong> <span style="color: #ef4444; font-weight: 700;">${conf.horizontalSeparationNm} NM</span> (min 5.0 NM)</div>
            <div><strong>Vertical Sep:</strong> <span style="color: #ef4444; font-weight: 700;">${conf.verticalSeparationFt} ft</span> (min 1,000 ft)</div>
            <div><strong>Severity:</strong> <span class="flight-category-pill ${conf.severity === 'CRITICAL' ? 'IFR' : 'MVFR'}">${conf.severity}</span></div>
          </div>
        </div>
      `;
      cpaMarker.bindPopup(cpaPopupContent);

      // Focus card
      if (focusBar) {
        const card = document.createElement('div');
        card.className = 'conflict-focus-card';
        card.innerHTML = `
          <div class="conflict-focus-header">
            <span>🚨 ${conf.conflictingCallsign}</span>
            <span style="color: ${color}; font-size: 0.68rem;">● Traffic Path</span>
          </div>
          <div class="conflict-focus-details">
            Fix: <strong>${conf.pointName || 'Enroute'}</strong> &bull; CPA ${conf.timeOfClosestApproach.substring(11, 19)} UTC<br>
            Separation: ${conf.horizontalSeparationNm} NM / ${conf.verticalSeparationFt} ft
          </div>
          <button type="button" class="btn-zoom-cpa" onclick="zoomToCpa(${conf.latitude}, ${conf.longitude})">🎯 Zoom to CPA</button>
        `;
        focusBar.appendChild(card);
      }
    });
  }

  if (bounds.length > 0) {
    gConflictsMap.fitBounds(L.latLngBounds(bounds).pad(0.18));
  }
}

window.zoomToCpa = function(lat, lon) {
  if (!gConflictsMap) return;
  gConflictsMap.setView([lat, lon], 10, { animate: true });
};

// ========================================================
// Aerodrome Weather & Active Runways Inspector Modal (#weatherInfoModal)
// ========================================================
async function loadWeatherModal(icao) {
  if (!icao) return;
  const icaoClean = icao.trim().toUpperCase();
  gWeatherModalAirport = icaoClean;
  const content = document.getElementById('weatherModalContent');
  const btnDep = document.getElementById('btnSetAsDeparture');
  const btnArr = document.getElementById('btnSetAsArrival');

  // Highlight active quick button
  document.querySelectorAll('.weather-quick-btn').forEach(b => {
    b.classList.toggle('active', b.getAttribute('data-icao') === icaoClean);
  });
  const input = document.getElementById('weatherIcaoInput');
  if (input) input.value = icaoClean;

  content.innerHTML = `<div class="weather-loading-msg">💨 Querying NOAA Aviation Weather Center for ${icaoClean}...</div>`;

  try {
    const res = await fetch(`/api/v1/weather/metar?icao=${encodeURIComponent(icaoClean)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const metar = data.metar;
    const taf = data.taf;
    const activeInfo = data.activeRunway;

    let html = `
      <!-- Aerodrome Header -->
      <div style="display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid var(--border-color); padding-bottom: 8px;">
        <div>
          <span style="font-size: 1.15rem; font-weight: 800; color: #fff;">${data.name || icaoClean} (${icaoClean})</span>
          <span style="font-size: 0.78rem; color: var(--text-muted); margin-left: 8px;">${data.country || 'AIP Aerodrome'} &bull; Elevation: ${data.elevation || 0} ft</span>
        </div>
        ${metar ? `<span class="flight-category-pill ${metar.flightCategory || 'VFR'}">${metar.flightCategory || 'VFR'}</span>` : ''}
      </div>
    `;

    // 1. Live NOAA METAR Card
    if (metar && metar.rawOb) {
      const wdirStr = metar.isVariableWind ? 'VRB' : (metar.windDirection !== null ? `${String(metar.windDirection).padStart(3, '0')}°` : 'Calm');
      const wspdStr = `${metar.windSpeedKnots} kt${metar.windGustKnots ? ' (Gusts ' + metar.windGustKnots + ' kt)' : ''}`;
      const tempStr = metar.tempC !== null && metar.tempC !== undefined ? `${metar.tempC}°C` : '--';
      const dewpStr = metar.dewpointC !== null && metar.dewpointC !== undefined ? `${metar.dewpointC}°C` : '--';
      const qnhStr = metar.altimeterHpa ? `${metar.altimeterHpa} hPa` : '--';

      html += `
        <div class="weather-card">
          <div class="weather-card-header">
            <span>📡 Real-Time NOAA METAR Observation</span>
            <span style="font-size: 0.7rem; color: var(--text-muted);">${metar.reportTime ? 'Observed ' + metar.reportTime : 'Live Report'}</span>
          </div>
          <div class="weather-raw-pre">${metar.rawOb}</div>
          <div class="decoded-grid">
            <div class="decoded-tile">
              <span class="decoded-label">Surface Wind</span>
              <span class="decoded-val">${wdirStr} @ ${wspdStr}</span>
            </div>
            <div class="decoded-tile">
              <span class="decoded-label">Flight Rules</span>
              <span class="decoded-val"><span class="flight-category-pill ${metar.flightCategory || 'VFR'}">${metar.flightCategory || 'VFR'}</span></span>
            </div>
            <div class="decoded-tile">
              <span class="decoded-label">Temperature / Dewp</span>
              <span class="decoded-val">${tempStr} / ${dewpStr}</span>
            </div>
            <div class="decoded-tile">
              <span class="decoded-label">Altimeter (QNH)</span>
              <span class="decoded-val">${qnhStr}</span>
            </div>
          </div>
        </div>
      `;
    } else {
      html += `
        <div class="weather-card">
          <div class="weather-card-header"><span>📡 NOAA METAR Observation</span></div>
          <div style="font-size: 0.8rem; color: var(--text-muted);">METAR currently unavailable for ${icaoClean}. Using standard calm-wind aerodrome profile.</div>
        </div>
      `;
    }

    // 2. Operational Runway Analysis Table
    if (activeInfo && activeInfo.allRunways && activeInfo.allRunways.length > 0) {
      let rwyRows = activeInfo.allRunways.map(r => {
        const isAct = r.isActive;
        const hwText = r.headwind >= 0 ? `+${r.headwind} kt Headwind` : `${r.headwind} kt Tailwind`;
        const hwColor = r.headwind >= 0 ? '#10b981' : '#ef4444';
        const xwText = `${Math.abs(r.crosswind)} kt Crosswind`;
        return `
          <tr class="${isAct ? 'active-row' : ''}">
            <td><strong>RWY ${r.designator}</strong></td>
            <td>${Math.round(r.heading)}°</td>
            <td style="color: ${hwColor}; font-weight: 600;">${hwText}</td>
            <td style="color: var(--text-muted);">${xwText}</td>
            <td>
              ${isAct ? '<span class="runway-badge-active">⭐ ACTIVE RUNWAY</span>' : '<span class="runway-badge-secondary">Secondary / Downwind</span>'}
            </td>
          </tr>
        `;
      }).join('');

      html += `
        <div class="weather-card">
          <div class="weather-card-header">
            <span>🛫 Operational Runway Wind Analysis & Active Selection</span>
            <span style="font-size: 0.72rem; color: #10b981; font-weight: 700;">Selected: RWY ${activeInfo.activeRunway}</span>
          </div>
          <div style="font-size: 0.78rem; color: #cbd5e1; margin-bottom: 8px; line-height: 1.4;">
            ${activeInfo.explanation || 'Calculated into the prevailing surface wind vector.'}
          </div>
          <table class="runway-table">
            <thead>
              <tr>
                <th>Runway</th>
                <th>Heading</th>
                <th>Headwind / Tailwind</th>
                <th>Crosswind</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              ${rwyRows}
            </tbody>
          </table>
        </div>
      `;
    }

    // 3. Live NOAA TAF Card
    if (taf && taf.rawTAF) {
      html += `
        <div class="weather-card">
          <div class="weather-card-header">
            <span>🔮 Terminal Aerodrome Forecast (TAF)</span>
            <span style="font-size: 0.7rem; color: var(--text-muted);">${taf.issueTime ? 'Issued ' + taf.issueTime : 'Forecast'}</span>
          </div>
          <div class="weather-raw-pre">${taf.rawTAF}</div>
        </div>
      `;
    }

    content.innerHTML = html;

    // Show action buttons
    if (btnDep) {
      btnDep.style.display = 'inline-flex';
      btnDep.textContent = `🛫 Set ${icaoClean} as Departure`;
      btnDep.onclick = () => {
        const depSelect = document.getElementById('depAirport');
        if (depSelect) {
          depSelect.value = icaoClean;
          updateRunwayOptions(icaoClean, 'depRunway');
        }
        document.getElementById('weatherInfoModal').classList.add('hidden');
      };
    }
    if (btnArr) {
      btnArr.style.display = 'inline-flex';
      btnArr.textContent = `🛬 Set ${icaoClean} as Arrival`;
      btnArr.onclick = () => {
        const arrSelect = document.getElementById('arrAirport');
        if (arrSelect) {
          arrSelect.value = icaoClean;
          updateRunwayOptions(icaoClean, 'arrRunway');
        }
        document.getElementById('weatherInfoModal').classList.add('hidden');
      };
    }
  } catch (err) {
    console.error('Weather load error:', err);
    content.innerHTML = `<div class="weather-loading-msg" style="color: #ef4444;">Failed to load NOAA weather for ${icaoClean}. Please verify connection.</div>`;
  }
}

// ========================================================
// Airport Runway Slot Management (ICAO Doc 4444 Wake Spacing)
// ========================================================

async function refreshDepartureSlots() {
  const depIcao = document.getElementById('depAirport').value;
  const eobtVal = document.getElementById('eobt').value;
  const acType = document.getElementById('aircraftType').value || 'A320';
  const depSelect = document.getElementById('depSlotSelect');
  const badge = document.getElementById('depSlotBadge');

  if (!depIcao || !eobtVal || !depSelect) return;

  const eobtDate = new Date(eobtVal);
  const dateStr = eobtDate.toISOString().substring(0, 10);

  try {
    const res = await fetch(`/api/v1/airports/${depIcao}/slots?date=${dateStr}&slotType=DEPARTURE&acType=${acType}`).then(r => r.json());
    if (!res.slots) return;

    depSelect.innerHTML = '<option value="">-- Select Departure Slot --</option>';

    const eobtTimeMs = eobtDate.getTime();
    // Show slots within -30 min to +90 min window around EOBT
    const relevantSlots = res.slots.filter(s => {
      const slotMs = new Date(s.startTime).getTime();
      return (slotMs - eobtTimeMs >= -30 * 60 * 1000) && (slotMs - eobtTimeMs <= 90 * 60 * 1000);
    });

    let currentSlotOccupied = false;

    relevantSlots.forEach(s => {
      const slotMs = new Date(s.startTime).getTime();
      const isCurrent = Math.abs(slotMs - eobtTimeMs) < 2.5 * 60 * 1000;
      const isAvail = s.status === 'AVAILABLE';
      const label = `${s.label} UTC - ${s.status}${s.allocatedCallsign ? ` (${s.allocatedCallsign})` : ''}${isCurrent ? ' ★ SELECTED' : ''}`;
      
      const opt = document.createElement('option');
      opt.value = s.startTime;
      opt.textContent = label;
      opt.disabled = !isAvail && !isCurrent;
      if (isCurrent) {
        opt.selected = true;
        if (!isAvail) currentSlotOccupied = true;
      }
      depSelect.appendChild(opt);
    });

    if (badge) {
      if (currentSlotOccupied) {
        badge.className = 'slot-badge occupied';
        badge.textContent = '🔴 Departure Slot Occupied (Runway / Wake Minimums Infringed)';
      } else {
        badge.className = 'slot-badge available';
        badge.textContent = '🟢 Departure Slot Available (ICAO Doc 4444 Wake OK)';
      }
    }
  } catch (err) {
    console.error('Error refreshing departure slots:', err);
  }
}

function updateArrivalSlotStatus(trajectory) {
  const notice = document.getElementById('arrSlotNotice');
  if (!notice || !trajectory || !trajectory.points || trajectory.points.length === 0) return;

  const pEnd = trajectory.points[trajectory.points.length - 1];
  const arrIcao = document.getElementById('arrAirport').value;
  const arrRwy = document.getElementById('arrRunway').value || 'AUTO';
  const overflightTime = pEnd.estimatedOverflightTime ? pEnd.estimatedOverflightTime.substring(11, 16) : '--:--';

  // Check if trajectory deconfliction detected an arrival runway conflict
  const hasArrConflict = trajectory.deconfliction && trajectory.deconfliction.conflicts &&
    trajectory.deconfliction.conflicts.some(c => c.conflictType === 'AIRPORT_ARRIVAL_SLOT_CONFLICT');

  if (hasArrConflict) {
    notice.className = 'slot-notice-inline error';
    notice.style.backgroundColor = 'rgba(239, 68, 68, 0.15)';
    notice.style.borderColor = 'rgba(239, 68, 68, 0.4)';
    notice.style.color = '#fca5a5';
    notice.innerHTML = `⚠️ <strong>Destination Arrival Conflict at ${arrIcao}:</strong> Runway ${arrRwy} wake vortex or slot occupancy infringed at ~${overflightTime} UTC. Use "Test 4D Conflicts" or choose an alternate departure slot.`;
  } else {
    notice.className = 'slot-notice-inline clear';
    notice.style.backgroundColor = 'rgba(16, 185, 129, 0.12)';
    notice.style.borderColor = 'rgba(16, 185, 129, 0.3)';
    notice.style.color = '#6ee7b7';
    notice.innerHTML = `🟢 <strong>Arrival Runway Slot Cleared:</strong> Estimated touchdown at <strong>${arrIcao} (RWY ${arrRwy})</strong> at <strong>${overflightTime} UTC</strong>. ICAO wake turbulence criteria satisfied.`;
  }
}

function openSlotBoardModal() {
  const modal = document.getElementById('slotBoardModal');
  if (!modal) return;
  modal.classList.remove('hidden');

  const curDep = document.getElementById('depAirport').value || 'EGLL';
  const airportSelect = document.getElementById('slotModalAirport');
  if (airportSelect) airportSelect.value = curDep;

  const eobtVal = document.getElementById('eobt').value;
  const dateInput = document.getElementById('slotModalDate');
  if (dateInput) {
    dateInput.value = eobtVal ? eobtVal.substring(0, 10) : new Date().toISOString().substring(0, 10);
  }

  loadAndRenderSlotBoard();
}

async function loadAndRenderSlotBoard() {
  const airport = document.getElementById('slotModalAirport').value || 'EGLL';
  const slotType = document.getElementById('slotModalType').value || 'DEPARTURE';
  const date = document.getElementById('slotModalDate').value || new Date().toISOString().substring(0, 10);
  const acType = document.getElementById('aircraftType').value || 'A320';
  const container = document.getElementById('slotGridContainer');

  container.innerHTML = '<div class="subtext text-center" style="padding: 30px;">Loading airport runway slots...</div>';

  try {
    const res = await fetch(`/api/v1/airports/${airport}/slots?date=${date}&slotType=${slotType}&acType=${acType}`).then(r => r.json());

    document.getElementById('statTotalSlots').textContent = res.summary ? res.summary.totalSlots : (res.slots ? res.slots.length : 0);
    document.getElementById('statAvailableSlots').textContent = res.summary ? res.summary.available : 0;
    document.getElementById('statOccupiedSlots').textContent = res.summary ? res.summary.occupied : 0;

    // Render Runway Operational Mode Notice
    const modeNotice = document.getElementById('slotAirportModeNotice');
    if (modeNotice) {
      const isParallel = res.isParallelSegregated;
      const mode = res.operationalMode || 'MIXED_MODE_SINGLE';
      const exot = res.taxiOutMinutes || 10;
      modeNotice.innerHTML = `
        <div style="display: flex; gap: 8px; align-items: center; background: rgba(30, 41, 59, 0.7); padding: 8px 12px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.08); flex-wrap: wrap;">
          <span class="swim-badge" style="background: ${isParallel ? 'rgba(16, 185, 129, 0.2)' : 'rgba(245, 158, 11, 0.2)'}; color: ${isParallel ? '#6ee7b7' : '#fcd34d'}; border: 1px solid ${isParallel ? 'rgba(16, 185, 129, 0.4)' : 'rgba(245, 158, 11, 0.4)'};">
            ${isParallel ? '⚡ PARALLEL SEGREGATED (ICAO Doc 9643 SOIR)' : '🔀 SINGLE RUNWAY MIXED-MODE'}
          </span>
          <span style="color: var(--text-muted); font-size: 0.75rem;">
            ${isParallel ? 'Independent parallel operations: departures do not require wake buffers against parallel arrivals.' : 'Single physical runway: requires arrival rollout buffer + wake turbulence decay between departures & arrivals.'}
          </span>
          <span style="margin-left: auto; color: var(--accent-cyan); font-weight: 600; font-size: 0.75rem;">EXOT: ${exot} min</span>
        </div>
      `;
    }

    if (!res.slots || res.slots.length === 0) {
      container.innerHTML = '<div class="subtext text-center" style="padding: 20px;">No runway slot schedule available for this date.</div>';
      return;
    }

    container.innerHTML = '';
    res.slots.forEach(slot => {
      const isAvail = slot.status === 'AVAILABLE';
      const card = document.createElement('div');
      card.className = `slot-card ${isAvail ? 'available' : 'occupied'}`;
      card.title = isAvail ? 'Click to select this runway slot' : `Occupied: ${slot.conflictReason || 'Wake vortex / occupancy'}`;

      const etotDisplay = slot.slotTimeEtot || slot.label;
      const eobtDisplay = slot.slotTimeEobt || '--:--';

      card.innerHTML = `
        <div class="slot-card-header">
          <span class="slot-time">🛫 ${etotDisplay} ETOT</span>
          <span class="slot-status-pill">${slot.status}</span>
        </div>
        <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 2px;">
          🚪 Pushback: <strong>${eobtDisplay} EOBT</strong>
        </div>
        ${slot.allocatedCallsign ? `
          <div class="slot-booking-info" style="margin-top: 4px;">
            ✈️ ${slot.allocatedCallsign} (${slot.allocatedAircraftType || 'CAT ' + slot.allocatedWakeCategory})
          </div>
        ` : `
          <div style="font-size: 0.68rem; color: #10b981; margin-top: 4px;">
            ✓ Available Slot
          </div>
        `}
      `;

      if (isAvail) {
        card.addEventListener('click', () => {
          selectSlotFromBoard(slot.startTime, slotType, airport, slot.eobt);
        });
      }

      container.appendChild(card);
    });
  } catch (err) {
    console.error('Error loading slot board:', err);
    container.innerHTML = `<div class="subtext text-center" style="color: #ef4444; padding: 20px;">Failed to load slot capacity board for ${airport}.</div>`;
  }
}

function selectSlotFromBoard(isoStartTime, slotType, airportIcao, slotEobtIso) {
  if (slotType === 'DEPARTURE') {
    const depSelect = document.getElementById('depAirport');
    if (depSelect) depSelect.value = airportIcao;
    const eobtInput = document.getElementById('eobt');
    if (eobtInput) {
      const targetTime = slotEobtIso ? new Date(slotEobtIso) : new Date(isoStartTime);
      eobtInput.value = formatLocalDateTime(targetTime);
    }
    closeModal('slotBoardModal');
    updateRunwayTimingRibbon();
    refreshDepartureSlots();
    calculateTrajectory();
  } else {
    alert(`Arrival slot ${isoStartTime.substring(11, 16)} UTC at ${airportIcao} selected. Adjust your departure time or cruising speed to target this touchdown time.`);
    closeModal('slotBoardModal');
  }
}

