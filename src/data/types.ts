import { LatLon } from '../geo/coordinates.js';

export interface Runway {
  designator: string;
  trueBearing?: string;
  dimensions?: string;
  surface?: string;
}

export interface Airport {
  icao: string;
  name: string;
  country: 'GB' | 'IE';
  coordinates: LatLon;
  elevationFeet: number;
  runways: Runway[];
  magneticVariation?: string;
}

export interface Waypoint {
  name: string;
  country: 'GB' | 'IE';
  coordinates: LatLon;
  details?: string;
  routes?: string[];
}

export interface AirwayWaypoint {
  name: string;
  coordinates: LatLon;
}

export interface AirwayRoute {
  routeDesignator: string;
  navigationSpecification: string;
  waypoints: AirwayWaypoint[];
}

export interface FirAirspace {
  airspaceId: string;
  country: 'GB' | 'IE';
  minFlightLevel: number;
  maxFlightLevel: number;
  vertices: LatLon[];
}

