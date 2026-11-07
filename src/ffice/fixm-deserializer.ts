/**
 * FIXM XML and JSON Deserializers for FF-ICE Flight Plans
 */
import { XMLParser } from 'fast-xml-parser';
import { FficeFlightPlan, TrajectoryDetails } from './types.js';
import { TrajectoryPoint4D, FirCrossingSummary } from '../performance/trajectory-calculator.js';

export function parseFixmJson(jsonString: string): FficeFlightPlan {
  const parsed = JSON.parse(jsonString);
  if (!parsed.gufi || !parsed.departure || !parsed.arrival) {
    throw new Error('Invalid FIXM JSON payload: Missing mandatory GUFI, departure, or arrival');
  }
  return parsed as FficeFlightPlan;
}

export function parseFixmXml(xmlString: string): FficeFlightPlan {
  const parser = new XMLParser({
    ignoreAttributes: false,
    attributeNamePrefix: '@_',
    removeNSPrefix: true // removes 'fx:' and 'fb:' prefixes for clean JS access
  });

  const parsed = parser.parse(xmlString);
  const flight = parsed.Flight || parsed['fx:Flight'];
  if (!flight) {
    throw new Error('Invalid FIXM XML: Root <Flight> or <fx:Flight> element not found');
  }

  const rawGufi = typeof flight.gufi === 'object' ? flight.gufi['#text'] : flight.gufi;
  const gufi = String(rawGufi || '').replace(/^urn:uuid:/i, '');

  const flightId = flight.flightIdentification || {};
  const aircraft = flight.aircraft || {};
  const caps = aircraft.capabilities || {};
  const dep = flight.departure || {};
  const arr = flight.arrival || {};
  const enRoute = flight.enRoute || {};
  const trajectoryProfile = flight.routeTrajectory?.trajectoryProfile || {};
  const rawAgreed = trajectoryProfile.agreedTrajectory?.point4D || [];
  const rawCrossings = enRoute.airspaceCrossings?.airspaceCrossing || [];

  const pointsArray = Array.isArray(rawAgreed) ? rawAgreed : [rawAgreed].filter(Boolean);
  const points4D: TrajectoryPoint4D[] = pointsArray.map((pt: any) => {
    let lat = 0;
    let lon = 0;
    if (pt.position?.pos) {
      const parts = String(pt.position.pos).trim().split(/\s+/);
      lat = parseFloat(parts[0]);
      lon = parseFloat(parts[1]);
    }

    const altFt = typeof pt.level?.altitude === 'object' ? pt.level.altitude['#text'] : pt.level?.altitude;
    const flStr = String(pt.level?.flightLevel || 'F000').replace(/^[Ff]/, '');
    const fl = parseInt(flStr, 10);

    const speed = typeof pt.speed?.groundSpeed === 'object' ? pt.speed.groundSpeed['#text'] : pt.speed?.groundSpeed;
    const dist = typeof pt.cumulativeDistance === 'object' ? pt.cumulativeDistance['#text'] : pt.cumulativeDistance;

    return {
      pointType: pt.pointType || 'WAYPOINT',
      identifier: pt.pointIdentifier || 'WPT',
      coordinates: { latitude: lat, longitude: lon },
      altitudeFeet: parseInt(String(altFt || 0), 10),
      flightLevel: fl,
      cumulativeDistanceNm: parseFloat(String(dist || 0)),
      groundSpeedKnots: parseInt(String(speed || 0), 10),
      cumulativeTimeSeconds: parseInt(String(pt.time?.elapsedSeconds || 0), 10),
      estimatedTimestamp: pt.time?.estimatedTime || '',
      pointSource: pt.pointSource || 'CALCULATED',
      associatedAirspace: pt.airspace || undefined
    };
  });

  const crossingsArray = Array.isArray(rawCrossings) ? rawCrossings : [rawCrossings].filter(Boolean);
  const airspaceCrossings: FirCrossingSummary[] = crossingsArray.map((c: any) => {
    const flStr = String(c.crossingLevel || 'F000').replace(/^[Ff]/, '');
    return {
      enteringAirspace: c.airspaceDesignator || '',
      point: { latitude: 0, longitude: 0 },
      flightLevel: parseInt(flStr, 10),
      timestamp: c.crossingTime || '',
      distanceFromStartNm: parseFloat(String(typeof c.distanceFromStart === 'object' ? c.distanceFromStart['#text'] : c.distanceFromStart || 0))
    };
  });

  const toc = points4D.find(p => p.pointType === 'TOC') || points4D[0] || {} as any;
  const tod = points4D.find(p => p.pointType === 'TOD') || points4D[points4D.length - 1] || {} as any;

  const trajectory: TrajectoryDetails = {
    points4D,
    topOfClimb: toc,
    topOfDescent: tod,
    totalDistanceNm: parseFloat(String(typeof trajectoryProfile.totalDistance === 'object' ? trajectoryProfile.totalDistance['#text'] : trajectoryProfile.totalDistance || 0)),
    totalFlightTimeMinutes: parseFloat(String(trajectoryProfile.totalFlightTimeMinutes || 0))
  };

  return {
    gufi,
    status: flight.flightStatus || 'PLANNED',
    messageType: flight.messageType || 'FILING',
    filingTime: flight.filingTime || new Date().toISOString(),
    flightIdentification: {
      aircraftIdentification: flightId.aircraftIdentification || 'UNTITLED',
      aircraftRegistration: flightId.aircraftRegistration || undefined
    },
    aircraft: {
      aircraftType: aircraft.aircraftType || 'A320',
      wakeTurbulence: aircraft.wakeTurbulenceCategory || 'M',
      capabilities: {
        standardEquipment: caps.standardEquipment || 'SDFGIRW/LB1',
        navigation: String(caps.navigationCapabilities || '').split(/\s+/).filter(Boolean),
        communication: String(caps.communicationCapabilities || '').split(/\s+/).filter(Boolean),
        surveillance: String(caps.surveillanceCapabilities || '').split(/\s+/).filter(Boolean)
      }
    },
    departure: {
      aerodrome: dep.aerodrome || '',
      runway: dep.runway || undefined,
      elevationFeet: parseInt(String(typeof dep.elevation === 'object' ? dep.elevation['#text'] : dep.elevation || 0), 10),
      estimatedOffBlockTime: dep.estimatedOffBlockTime || ''
    },
    arrival: {
      aerodrome: arr.aerodrome || '',
      runway: arr.runway || undefined,
      elevationFeet: parseInt(String(typeof arr.elevation === 'object' ? arr.elevation['#text'] : arr.elevation || 0), 10),
      estimatedTimeOfArrival: arr.estimatedTimeOfArrival || ''
    },
    enRoute: {
      cruisingLevel: enRoute.cruisingLevel || 'F000',
      cruisingSpeed: typeof enRoute.cruisingSpeed === 'object' ? enRoute.cruisingSpeed['#text'] : enRoute.cruisingSpeed || 'N0450',
      routeString: enRoute.routeString || '',
      airspaceCrossings
    },
    trajectory,
    remarks: flight.remarks || undefined
  };
}

