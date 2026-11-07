import path from 'path';
import { Airport, Waypoint, AirwayRoute, FirAirspace } from './types.js';
import { loadAirports } from './airport-loader.js';
import { loadWaypoints } from './waypoint-loader.js';
import { loadRoutes } from './route-loader.js';
import { loadFirs } from './fir-loader.js';
import { LatLon } from '../geo/coordinates.js';
import { calculateDistanceNm } from '../geo/distance.js';
import { isPointIn3DAirspace } from '../geo/fir-spatial.js';

export interface AeroStoreOptions {
  baseDir?: string;
}

export class AeroStore {
  private airports = new Map<string, Airport>();
  private waypoints = new Map<string, Waypoint>();
  private routes = new Map<string, AirwayRoute>();
  private firs = new Map<string, FirAirspace>();
  private initialized = false;

  constructor(private options: AeroStoreOptions = {}) {}

  /**
   * Initializes the in-memory aeronautical database by parsing raw files.
   */
  async initialize(): Promise<void> {
    if (this.initialized) return;

    const base = this.options.baseDir || process.cwd();
    const airportsDir = path.join(base, 'airports');
    const waypointsDir = path.join(base, 'Waypoints');
    const routesFile = path.join(base, 'routes.txt');
    const firFile = path.join(base, 'FIR', 'FIR.csv');

    this.airports = loadAirports(airportsDir, base);
    this.waypoints = loadWaypoints(waypointsDir);
    this.routes = loadRoutes(routesFile);
    this.firs = await loadFirs(firFile);

    this.initialized = true;
  }

  // --- Airports ---
  getAirport(icao: string): Airport | undefined {
    return this.airports.get(icao.toUpperCase());
  }

  getAllAirports(): Airport[] {
    return Array.from(this.airports.values());
  }

  searchAirports(query: string, limit = 10): Airport[] {
    const q = query.trim().toUpperCase();
    if (!q) return this.getAllAirports().slice(0, limit);

    return this.getAllAirports()
      .filter(a => a.icao.includes(q) || a.name.toUpperCase().includes(q))
      .slice(0, limit);
  }

  // --- Waypoints ---
  getWaypoint(name: string): Waypoint | undefined {
    return this.waypoints.get(name.toUpperCase());
  }

  getAllWaypoints(): Waypoint[] {
    return Array.from(this.waypoints.values());
  }

  searchWaypoints(query: string, nearCoords?: LatLon, limit = 15): Waypoint[] {
    const q = query.trim().toUpperCase();
    let matches = this.getAllWaypoints().filter(w => w.name.includes(q));

    if (nearCoords) {
      matches.sort((a, b) => {
        const da = calculateDistanceNm(nearCoords, a.coordinates);
        const db = calculateDistanceNm(nearCoords, b.coordinates);
        return da - db;
      });
    }

    return matches.slice(0, limit);
  }

  // --- Routes ---
  getRoute(designator: string): AirwayRoute | undefined {
    return this.routes.get(designator.toUpperCase());
  }

  getAllRoutes(): AirwayRoute[] {
    return Array.from(this.routes.values());
  }

  // --- FIR Airspaces ---
  getFir(id: string): FirAirspace | undefined {
    return this.firs.get(id.toUpperCase());
  }

  getAllFirs(): FirAirspace[] {
    return Array.from(this.firs.values());
  }

  /**
   * Identifies all 3D FIR airspaces that contain a given 3D position (lat, lon, altFt).
   */
  findFirsForPoint(point: LatLon, altitudeFeet: number): FirAirspace[] {
    const matched: FirAirspace[] = [];
    for (const fir of this.firs.values()) {
      if (isPointIn3DAirspace(point, altitudeFeet, fir)) {
        matched.push(fir);
      }
    }
    return matched;
  }

  getStats() {
    return {
      airportsCount: this.airports.size,
      waypointsCount: this.waypoints.size,
      routesCount: this.routes.size,
      firsCount: this.firs.size
    };
  }
}

