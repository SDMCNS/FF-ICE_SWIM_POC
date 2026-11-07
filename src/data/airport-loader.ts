import fs from 'fs';
import path from 'path';
import { Airport, Runway } from './types.js';
import { parseCoordinates, parseElevationFeet } from '../geo/coordinates.js';

/**
 * Loads and normalizes all UK and Irish airports.
 */
export function loadAirports(airportsDir: string, rootDir?: string): Map<string, Airport> {
  const airports = new Map<string, Airport>();

  if (!fs.existsSync(airportsDir)) {
    throw new Error(`Airports directory not found at: ${airportsDir}`);
  }

  const files = fs.readdirSync(airportsDir);

  for (const file of files) {
    const fullPath = path.join(airportsDir, file);
    const stat = fs.statSync(fullPath);
    if (!stat.isFile()) continue;

    try {
      if (!file.endsWith('.json') && !file.endsWith('.txt')) continue;
      const content = fs.readFileSync(fullPath, 'utf8');
      const data = JSON.parse(content);

      const airport = parseUkAirportJson(data) || parseIrishAirportJson(data) || parseUkAipFullJson(data) || parseGenericAirportJson(data, file);
      if (airport) airports.set(airport.icao, airport);
    } catch (err) {
      // Ignore non-json or corrupt auxiliary files
    }
  }

  // Also check if root contains EGLL.txt or any standalone airport txt/json
  if (rootDir) {
    try {
      const rootFiles = fs.readdirSync(rootDir);
      for (const rf of rootFiles) {
        if (/^[A-Z]{4}\.(txt|json)$/i.test(rf)) {
          const egllPath = path.join(rootDir, rf);
          try {
            const content = fs.readFileSync(egllPath, 'utf8');
            const data = JSON.parse(content);
            const a = parseUkAipFullJson(data) || parseUkAirportJson(data) || parseIrishAirportJson(data) || parseGenericAirportJson(data, rf);
            if (a && !airports.has(a.icao)) airports.set(a.icao, a);
          } catch (e) {
            // fallback
          }
        }
      }
    } catch (e) {
      // ignore
    }
  }

  return airports;
}

function parseUkAirportJson(data: any): Airport | null {
  const icao = data.icao_code || (data.aerodrome && typeof data.aerodrome === 'string' ? data.aerodrome.match(/\(([A-Z]{4})\)/)?.[1] : null);
  if (!icao) return null;

  let coords;
  if (data.arp_coordinates) {
    coords = parseCoordinates(data.arp_coordinates.latitude, data.arp_coordinates.longitude);
  } else {
    return null;
  }

  const elevationFeet = parseElevationFeet(data.elevation);
  const runways: Runway[] = [];

  if (Array.isArray(data.runways)) {
    for (const r of data.runways) {
      const des = r.designation || r.designator;
      if (des && !runways.some(existing => existing.designator === des)) {
        runways.push({
          designator: des,
          trueBearing: r.true_bearing,
          dimensions: r.dimensions,
          surface: r.surface || r.strength_and_surface
        });
      }
    }
  }

  return {
    icao,
    name: typeof data.aerodrome === 'string' ? data.aerodrome.replace(/\s*\([A-Z]{4}\)/, '').trim() : icao,
    country: 'GB',
    coordinates: coords,
    elevationFeet,
    runways,
    magneticVariation: data.magnetic_variation
  };
}

function parseIrishAirportJson(data: any): Airport | null {
  const icao = data.aerodrome_identifier;
  if (!icao) return null;

  const geoAdmin = data.geographical_and_administrative_data || {};
  const arpStr = geoAdmin.arp_coordinates;
  if (!arpStr) return null;

  const coords = parseCoordinates(arpStr);
  const elevationFeet = parseElevationFeet(geoAdmin.elevation_reference_temperature_mean_low);

  const runways: Runway[] = [];
  const rwyList = data.runway_physical_characteristics || [];
  if (Array.isArray(rwyList)) {
    for (const r of rwyList) {
      const des = r.designation || r.designator;
      if (des && !runways.some(existing => existing.designator === des)) {
        runways.push({
          designator: des,
          trueBearing: r.true_bearing,
          dimensions: r.dimensions,
          surface: r.strength_and_surface
        });
      }
    }
  }

  return {
    icao,
    name: data.name || icao,
    country: 'IE',
    coordinates: coords,
    elevationFeet,
    runways,
    magneticVariation: geoAdmin.magnetic_variation
  };
}

function parseUkAipFullJson(data: any): Airport | null {
  const aero = data.aerodrome;
  if (!aero) return null;

  const icao = aero.indicator;
  if (!icao) return null;

  const geo = aero.geographical_and_administrative || {};
  const arp = geo.arp_coordinates;
  if (!arp) return null;

  const coords = parseCoordinates(arp.latitude, arp.longitude);
  const elevationFeet = parseElevationFeet(geo.elevation);

  const runways: Runway[] = [];
  if (Array.isArray(aero.runways)) {
    for (const r of aero.runways) {
      const des = r.designator || r.designation;
      if (des && !runways.some(existing => existing.designator === des)) {
        runways.push({
          designator: des,
          trueBearing: r.true_bearing,
          dimensions: r.dimensions,
          surface: r.surface
        });
      }
    }
  }

  return {
    icao,
    name: aero.name || icao,
    country: 'GB',
    coordinates: coords,
    elevationFeet,
    runways,
    magneticVariation: geo.magnetic_variation
  };
}

function parseGenericAirportJson(data: any, filename: string): Airport | null {
  if (!data || typeof data !== 'object') return null;
  const icao = data.icao || data.icao_code || data.ident || data.aerodrome_identifier || filename.match(/\b([A-Z]{4})\b/i)?.[1]?.toUpperCase();
  if (!icao) return null;

  let coords;
  const arp = data.arp_coordinates || data.coordinates || data.geographical_and_administrative_data?.arp_coordinates;
  if (arp) {
    if (typeof arp === 'object' && arp.latitude && arp.longitude) {
      coords = parseCoordinates(arp.latitude, arp.longitude);
    } else if (typeof arp === 'string') {
      coords = parseCoordinates(arp);
    }
  } else if (data.latitude && data.longitude) {
    coords = { latitude: parseFloat(data.latitude), longitude: parseFloat(data.longitude) };
  }
  if (!coords) return null;

  const elevationFeet = parseElevationFeet(data.elevation || data.elevationFeet || 0);
  const runways: Runway[] = [];
  const rawList = data.runways || data.runway_physical_characteristics || [];
  if (Array.isArray(rawList)) {
    for (const r of rawList) {
      const des = r.designator || r.designation;
      if (des && !runways.some(existing => existing.designator === des)) {
        runways.push({
          designator: des,
          trueBearing: r.true_bearing || r.trueBearing,
          dimensions: r.dimensions,
          surface: r.surface || r.strength_and_surface
        });
      }
    }
  }

  let country = data.country;
  if (!country) {
    if (icao.startsWith('EI')) country = 'IE';
    else if (icao.startsWith('EG')) country = 'GB';
    else if (icao.startsWith('LF')) country = 'FR';
    else if (icao.startsWith('ED')) country = 'DE';
    else if (icao.startsWith('EH')) country = 'NL';
    else if (icao.startsWith('K')) country = 'US';
    else country = icao.substring(0, 2);
  }

  return {
    icao,
    name: data.name || data.aerodrome?.replace(/\s*\([A-Z]{4}\)/, '') || icao,
    country,
    coordinates: coords,
    elevationFeet,
    runways
  };
}

