import fs from 'fs';
import { AirwayRoute } from './types.js';
import { parseCoordinates } from '../geo/coordinates.js';

/**
 * Loads airway routes from routes.txt.
 */
export function loadRoutes(routesFilePath: string): Map<string, AirwayRoute> {
  const routes = new Map<string, AirwayRoute>();

  if (!fs.existsSync(routesFilePath)) {
    return routes;
  }

  try {
    const content = fs.readFileSync(routesFilePath, 'utf8');
    const data = JSON.parse(content);

    if (Array.isArray(data)) {
      for (const item of data) {
        const des = item.route_designator;
        if (!des) continue;

        const waypoints = [];
        if (Array.isArray(item.waypoints)) {
          for (const wp of item.waypoints) {
            try {
              const coords = parseCoordinates(wp.coordinates);
              waypoints.push({
                name: wp.name,
                coordinates: coords
              });
            } catch (e) {
              // skip waypoint if coordinates fail
            }
          }
        }

        routes.set(des, {
          routeDesignator: des,
          navigationSpecification: item.navigation_specification || 'RNAV 5',
          waypoints
        });
      }
    }
  } catch (err) {
    console.warn(`Error reading routes file at ${routesFilePath}:`, err);
  }

  return routes;
}

