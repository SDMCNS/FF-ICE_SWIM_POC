/**
 * FF-ICE Release 1/2 & FIXM v4.2+ Domain Type Definitions
 */
import { LatLon } from '../geo/coordinates.js';
import { TrajectoryPoint4D, FirCrossingSummary } from '../performance/trajectory-calculator.js';

export type FficeFlightStatus = 
  | 'PLANNED'
  | 'FILED'
  | 'NEGOTIATING'
  | 'AGREED'
  | 'ACTIVE'
  | 'COMPLETED'
  | 'CANCELLED';

export type FficeMessageType =
  | 'FILING'
  | 'PRELIMINARY'
  | 'MODIFICATION'
  | 'CANCELLATION'
  | 'TRIAL_REQUEST'
  | 'TRAJECTORY_ADVISORY';

export interface AircraftCapabilities {
  standardEquipment: string; // e.g. "SDFGIRW/LB1"
  navigation: string[];      // e.g. ["RNAV 1", "RNAV 5", "RNP 4"]
  communication: string[];   // e.g. ["VHF 8.33 kHz", "CPDLC"]
  surveillance: string[];    // e.g. ["ADS-B Out", "Mode S Transponder"]
}

export interface FlightIdentification {
  aircraftIdentification: string; // Callsign (e.g. "EIN123", "BAW456")
  aircraftRegistration?: string;  // Registration (e.g. "EI-DVM", "G-EUPA")
}

export interface AircraftDetails {
  aircraftType: string;           // ICAO type code (e.g. "A320")
  wakeTurbulence: 'L' | 'M' | 'H' | 'J';
  capabilities: AircraftCapabilities;
}

export interface DepartureDetails {
  aerodrome: string;              // ICAO code (e.g. "EGLL")
  runway?: string;
  elevationFeet: number;
  estimatedOffBlockTime: string;  // ISO 8601 UTC
}

export interface ArrivalDetails {
  aerodrome: string;              // ICAO code (e.g. "EIDW")
  runway?: string;
  elevationFeet: number;
  estimatedTimeOfArrival: string; // ISO 8601 UTC
}

export interface EnRouteDetails {
  cruisingLevel: string;          // e.g. "F280"
  cruisingSpeed: string;          // e.g. "N0450" (450 KTAS)
  routeString: string;            // e.g. "EGLL LIPGO EIDW"
  airspaceCrossings: FirCrossingSummary[];
}

export interface TrajectoryDetails {
  points4D: TrajectoryPoint4D[];
  topOfClimb: TrajectoryPoint4D;
  topOfDescent: TrajectoryPoint4D;
  totalDistanceNm: number;
  totalFlightTimeMinutes: number;
}

export interface FficeFlightPlan {
  gufi: string;                   // Globally Unique Flight Identifier (UUID v4)
  status: FficeFlightStatus;
  messageType: FficeMessageType;
  filingTime: string;             // ISO 8601 UTC
  flightIdentification: FlightIdentification;
  aircraft: AircraftDetails;
  departure: DepartureDetails;
  arrival: ArrivalDetails;
  enRoute: EnRouteDetails;
  trajectory: TrajectoryDetails;
  remarks?: string;
}

