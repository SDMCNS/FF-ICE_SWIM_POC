/**
 * Aircraft Performance Profiles and Specifications for Trajectory Generation
 */

export interface AircraftPerformance {
  icaoType: string;
  manufacturer: string;
  model: string;
  wakeTurbulenceCategory: 'L' | 'M' | 'H' | 'J'; // Light, Medium, Heavy, Super
  defaultEquipment: string; // ICAO / FF-ICE equipment codes (e.g. SDFGIRW/LB1)
  serviceCeilingFl: number; // e.g. 390 = FL390 (39,000 ft)
  typicalCruiseFl: number;  // e.g. 340
  cruiseTasKnots: number;   // True Airspeed in knots
  cruiseMach: number;       // Typical Mach number

  // Climb characteristics
  averageClimbRateFpm: number;  // Feet per minute (e.g. 2200 fpm)
  averageClimbSpeedKnots: number; // Average ground speed in climb (e.g. 300 kts)

  // Descent characteristics
  averageDescentRateFpm: number; // Feet per minute (e.g. 2000 fpm)
  averageDescentSpeedKnots: number; // Average ground speed in descent (e.g. 280 kts)
  descentGradientFtPerNm: number;  // Typically 318 ft/NM (~3 degree slope)
}

export const AIRCRAFT_DATABASE: Record<string, AircraftPerformance> = {
  A320: {
    icaoType: 'A320',
    manufacturer: 'Airbus',
    model: 'A320-200 / neo',
    wakeTurbulenceCategory: 'M',
    defaultEquipment: 'SDFGIRW/LB1',
    serviceCeilingFl: 390,
    typicalCruiseFl: 340,
    cruiseTasKnots: 450,
    cruiseMach: 0.78,
    averageClimbRateFpm: 2200,
    averageClimbSpeedKnots: 320,
    averageDescentRateFpm: 2000,
    averageDescentSpeedKnots: 290,
    descentGradientFtPerNm: 318
  },
  B738: {
    icaoType: 'B738',
    manufacturer: 'Boeing',
    model: '737-800 / MAX 8',
    wakeTurbulenceCategory: 'M',
    defaultEquipment: 'SDFGIRW/LB1',
    serviceCeilingFl: 410,
    typicalCruiseFl: 360,
    cruiseTasKnots: 455,
    cruiseMach: 0.79,
    averageClimbRateFpm: 2300,
    averageClimbSpeedKnots: 325,
    averageDescentRateFpm: 2000,
    averageDescentSpeedKnots: 295,
    descentGradientFtPerNm: 318
  },
  A321: {
    icaoType: 'A321',
    manufacturer: 'Airbus',
    model: 'A321-200 / neo',
    wakeTurbulenceCategory: 'M',
    defaultEquipment: 'SDFGIRW/LB1',
    serviceCeilingFl: 390,
    typicalCruiseFl: 350,
    cruiseTasKnots: 455,
    cruiseMach: 0.79,
    averageClimbRateFpm: 2100,
    averageClimbSpeedKnots: 320,
    averageDescentRateFpm: 2000,
    averageDescentSpeedKnots: 290,
    descentGradientFtPerNm: 318
  },
  E190: {
    icaoType: 'E190',
    manufacturer: 'Embraer',
    model: 'E190 / E195-E2',
    wakeTurbulenceCategory: 'M',
    defaultEquipment: 'SDFGIRW/LB1',
    serviceCeilingFl: 410,
    typicalCruiseFl: 340,
    cruiseTasKnots: 430,
    cruiseMach: 0.77,
    averageClimbRateFpm: 2000,
    averageClimbSpeedKnots: 300,
    averageDescentRateFpm: 1900,
    averageDescentSpeedKnots: 280,
    descentGradientFtPerNm: 318
  },
  AT76: {
    icaoType: 'AT76',
    manufacturer: 'ATR',
    model: '72-600',
    wakeTurbulenceCategory: 'M',
    defaultEquipment: 'SDFGIR/S',
    serviceCeilingFl: 250,
    typicalCruiseFl: 200,
    cruiseTasKnots: 275,
    cruiseMach: 0.42,
    averageClimbRateFpm: 1200,
    averageClimbSpeedKnots: 190,
    averageDescentRateFpm: 1500,
    averageDescentSpeedKnots: 210,
    descentGradientFtPerNm: 300
  },
  DH8D: {
    icaoType: 'DH8D',
    manufacturer: 'De Havilland Canada',
    model: 'Dash 8-400 (Q400)',
    wakeTurbulenceCategory: 'M',
    defaultEquipment: 'SDFGIR/S',
    serviceCeilingFl: 270,
    typicalCruiseFl: 240,
    cruiseTasKnots: 340,
    cruiseMach: 0.52,
    averageClimbRateFpm: 1500,
    averageClimbSpeedKnots: 230,
    averageDescentRateFpm: 1600,
    averageDescentSpeedKnots: 240,
    descentGradientFtPerNm: 300
  },
  B77W: {
    icaoType: 'B77W',
    manufacturer: 'Boeing',
    model: '777-300ER',
    wakeTurbulenceCategory: 'H',
    defaultEquipment: 'SDE2E3FGIJ1J2J3J4J5RW/LB1',
    serviceCeilingFl: 430,
    typicalCruiseFl: 360,
    cruiseTasKnots: 490,
    cruiseMach: 0.84,
    averageClimbRateFpm: 2400,
    averageClimbSpeedKnots: 340,
    averageDescentRateFpm: 2200,
    averageDescentSpeedKnots: 300,
    descentGradientFtPerNm: 318
  },
  A359: {
    icaoType: 'A359',
    manufacturer: 'Airbus',
    model: 'A350-900',
    wakeTurbulenceCategory: 'H',
    defaultEquipment: 'SDE2E3FGIJ1J2J3J4J5RW/LB1',
    serviceCeilingFl: 430,
    typicalCruiseFl: 380,
    cruiseTasKnots: 490,
    cruiseMach: 0.85,
    averageClimbRateFpm: 2500,
    averageClimbSpeedKnots: 345,
    averageDescentRateFpm: 2200,
    averageDescentSpeedKnots: 300,
    descentGradientFtPerNm: 318
  },
  C172: {
    icaoType: 'C172',
    manufacturer: 'Cessna',
    model: '172 Skyhawk',
    wakeTurbulenceCategory: 'L',
    defaultEquipment: 'SGR/C',
    serviceCeilingFl: 140,
    typicalCruiseFl: 60,
    cruiseTasKnots: 110,
    cruiseMach: 0.17,
    averageClimbRateFpm: 600,
    averageClimbSpeedKnots: 75,
    averageDescentRateFpm: 600,
    averageDescentSpeedKnots: 90,
    descentGradientFtPerNm: 250
  }
};

export function getAircraftPerformance(icaoType: string): AircraftPerformance {
  const normalized = icaoType.trim().toUpperCase();
  const perf = AIRCRAFT_DATABASE[normalized];
  if (perf) return perf;

  // Fallback to generic medium jet (A320 equivalent)
  return {
    ...AIRCRAFT_DATABASE['A320'],
    icaoType: normalized,
    model: `Generic (${normalized})`
  };
}

