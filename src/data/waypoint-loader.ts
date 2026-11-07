import fs from 'fs';
import path from 'path';
import { Waypoint } from './types.js';
import { parseCoordinates } from '../geo/coordinates.js';

/**
 * Loads waypoints from the Waypoints folder (location-agnostic, supporting any region or country).
 */
export function loadWaypoints(waypointsDir: string): Map<string, Waypoint> {
  const waypoints = new Map<string, Waypoint>();
  if (!fs.existsSync(waypointsDir)) return waypoints;

  const files = fs.readdirSync(waypointsDir);

  for (const file of files) {
    if (!file.endsWith('.json') && !file.endsWith('.txt')) continue;
    const fullPath = path.join(waypointsDir, file);

    try {
      const data = JSON.parse(fs.readFileSync(fullPath, 'utf8'));
      const items = Array.isArray(data) ? data : (data.waypoints || []);

      if (Array.isArray(items)) {
        for (const item of items) {
          const name = item.name_code_designator || item.name || item.ident || item.id;
          if (!name) continue;
          const cleanName = String(name).trim().toUpperCase();
          if (waypoints.has(cleanName)) continue;

          let coords;
          if (item.coordinates) {
            if (typeof item.coordinates === 'object' && item.coordinates.latitude && item.coordinates.longitude) {
              coords = parseCoordinates(item.coordinates.latitude, item.coordinates.longitude);
            } else if (typeof item.coordinates === 'string') {
              coords = parseCoordinates(item.coordinates);
            }
          } else if (item.latitude && item.longitude) {
            coords = { latitude: parseFloat(item.latitude), longitude: parseFloat(item.longitude) };
          }

          if (!coords) continue;

          const routes: string[] = [];
          const detailsStr = item.details || item.remarks || item.ats_route_or_other_route || '';
          if (typeof detailsStr === 'string') {
            const matches = detailsStr.match(/\b([A-Z][0-9]{1,4})\b/g);
            if (matches) routes.push(...matches);
          }

          let country = item.country;
          if (!country) {
            if (/IE/i.test(file)) country = 'IE';
            else if (/UK|GB/i.test(file)) country = 'GB';
            else country = 'XX';
          }

          waypoints.set(cleanName, {
            name: cleanName,
            country,
            coordinates: coords,
            details: detailsStr || undefined,
            routes: Array.from(new Set(routes))
          });
        }
      }
    } catch (e) {
      console.warn(`Error reading waypoints from ${fullPath}:`, e);
    }
  }

  return waypoints;
}

