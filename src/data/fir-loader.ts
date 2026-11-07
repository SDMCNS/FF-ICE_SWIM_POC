import fs from 'fs';
import readline from 'readline';
import { FirAirspace } from './types.js';
import { LatLon } from '../geo/coordinates.js';

interface FirRow {
  airspaceId: string;
  minFL: number;
  maxFL: number;
  seq: number;
  lat: number;
  lon: number;
}

/**
 * Loads UK (EG*) and Irish (EI*) FIR boundaries from FIR.csv.
 */
export async function loadFirs(firCsvPath: string): Promise<Map<string, FirAirspace>> {
  const firs = new Map<string, FirAirspace>();

  if (!fs.existsSync(firCsvPath)) {
    console.warn(`FIR.csv file not found at: ${firCsvPath}`);
    return firs;
  }

  const fileStream = fs.createReadStream(firCsvPath);
  const rl = readline.createInterface({
    input: fileStream,
    crlfDelay: Infinity
  });

  const rowsByAirspace = new Map<string, FirRow[]>();

  for await (const line of rl) {
    if (!line || line.startsWith('"Airspace ID"')) continue;

    // Filter only UK and Irish airspaces starting with "EG" or "EI"
    if (!line.startsWith('"EG') && !line.startsWith('"EI') && !line.startsWith('EG') && !line.startsWith('EI')) {
      continue;
    }

    const parts = line.split(',').map(s => s.replace(/^"|"$/g, '').trim());
    if (parts.length < 6) continue;

    const airspaceId = parts[0];
    const minFL = parseInt(parts[1], 10);
    const maxFL = parseInt(parts[2], 10);
    const seq = parseInt(parts[3], 10);
    const lat = parseFloat(parts[4]);
    const lon = parseFloat(parts[5]);

    if (isNaN(lat) || isNaN(lon)) continue;

    if (!rowsByAirspace.has(airspaceId)) {
      rowsByAirspace.set(airspaceId, []);
    }

    rowsByAirspace.get(airspaceId)!.push({
      airspaceId,
      minFL,
      maxFL,
      seq,
      lat,
      lon
    });
  }

  // Construct polygons sorted by sequence number
  for (const [id, rows] of rowsByAirspace.entries()) {
    rows.sort((a, b) => a.seq - b.seq);
    const vertices: LatLon[] = rows.map(r => ({
      latitude: r.lat,
      longitude: r.lon
    }));

    const first = rows[0];
    const country = id.startsWith('EI') ? 'IE' : 'GB';

    firs.set(id, {
      airspaceId: id,
      country,
      minFlightLevel: isNaN(first.minFL) ? 0 : first.minFL,
      maxFlightLevel: isNaN(first.maxFL) ? 999 : first.maxFL,
      vertices
    });
  }

  return firs;
}

