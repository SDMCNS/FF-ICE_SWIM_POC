/**
 * SWIM Flight Planning and Trajectory Information Service
 * Implements ICAO Doc 10039 SWIM Information Service Patterns
 */
import { AeroStore } from '../data/aero-store.js';
import { FficeFlightPlan, FficeFlightStatus } from '../ffice/types.js';
import { generateGufi, isValidGufi } from '../ffice/gufi.js';
import { validateFficeFlightPlan, ValidationReport } from '../ffice/validator.js';
import { calculate4DTrajectory, CalculatedTrajectory, TrajectoryCalculationRequest } from '../performance/trajectory-calculator.js';
import { getAircraftPerformance, AIRCRAFT_DATABASE } from '../performance/aircraft-database.js';
import { serializeToFixmXml, serializeToFixmJson } from '../ffice/fixm-serializer.js';
import { parseFixmXml, parseFixmJson } from '../ffice/fixm-deserializer.js';

export interface PlanListFilter {
  callsign?: string;
  departure?: string;
  arrival?: string;
  status?: string;
}

export interface TrajectoryServiceParams {
  departureIcao: string;
  departureRunway?: string;
  arrivalIcao: string;
  arrivalRunway?: string;
  aircraftType: string;
  requestedCruiseFl: number;
  waypointNames?: string[];
  estimatedOffBlockTime?: string;
  callsign?: string;
}

export class SwimFlightPlanService {
  private plans = new Map<string, FficeFlightPlan>();

  constructor(private store: AeroStore) {}

  async initialize(): Promise<void> {
    await this.store.initialize();
  }

  getAeroStore(): AeroStore {
    return this.store;
  }

  /**
   * Calculates a 4D Trajectory and provides flight sanity advice.
   */
  calculateTrajectory(params: TrajectoryServiceParams): {
    calculated: CalculatedTrajectory;
    departureAirport: any;
    arrivalAirport: any;
  } {
    const dep = this.store.getAirport(params.departureIcao);
    if (!dep) {
      throw new Error(`Departure aerodrome "${params.departureIcao}" not found in database.`);
    }

    const arr = this.store.getAirport(params.arrivalIcao);
    if (!arr) {
      throw new Error(`Arrival aerodrome "${params.arrivalIcao}" not found in database.`);
    }

    const aircraft = getAircraftPerformance(params.aircraftType);

    const waypoints = (params.waypointNames || []).map(name => {
      const wp = this.store.getWaypoint(name);
      if (!wp) {
        throw new Error(`Waypoint "${name}" not found in database.`);
      }
      return wp;
    });

    const calculated = calculate4DTrajectory({
      departure: dep,
      destination: arr,
      waypoints,
      aircraft,
      requestedCruiseFl: params.requestedCruiseFl,
      estimatedOffBlockTime: params.estimatedOffBlockTime || new Date().toISOString()
    }, this.store.getAllFirs());

    return {
      calculated,
      departureAirport: dep,
      arrivalAirport: arr
    };
  }

  /**
   * Files a new FF-ICE Flight Plan.
   */
  filePlan(plan: Partial<FficeFlightPlan>): { plan: FficeFlightPlan; validation: ValidationReport } {
    const gufi = plan.gufi && isValidGufi(plan.gufi) ? plan.gufi : generateGufi();

    const fullPlan: FficeFlightPlan = {
      gufi,
      status: (plan.status as FficeFlightStatus) || 'FILED',
      messageType: plan.messageType || 'FILING',
      filingTime: plan.filingTime || new Date().toISOString(),
      flightIdentification: {
        aircraftIdentification: plan.flightIdentification?.aircraftIdentification || 'UNTITLED',
        aircraftRegistration: plan.flightIdentification?.aircraftRegistration
      },
      aircraft: {
        aircraftType: plan.aircraft?.aircraftType || 'A320',
        wakeTurbulence: plan.aircraft?.wakeTurbulence || 'M',
        capabilities: plan.aircraft?.capabilities || {
          standardEquipment: 'SDFGIRW/LB1',
          navigation: ['RNAV 1', 'RNAV 5', 'RNP 4'],
          communication: ['VHF 8.33 kHz', 'CPDLC'],
          surveillance: ['ADS-B Out', 'Mode S Transponder']
        }
      },
      departure: plan.departure!,
      arrival: plan.arrival!,
      enRoute: plan.enRoute!,
      trajectory: plan.trajectory!,
      remarks: plan.remarks
    };

    const validation = validateFficeFlightPlan(fullPlan);
    if (!validation.isValid) {
      const errMsgs = validation.issues.filter(i => i.severity === 'ERROR').map(i => i.message).join('; ');
      throw new Error(`FF-ICE Validation Failed: ${errMsgs}`);
    }

    this.plans.set(gufi, fullPlan);
    return { plan: fullPlan, validation };
  }

  /**
   * Retrieves a flight plan by GUFI.
   */
  getPlan(gufi: string): FficeFlightPlan | undefined {
    const clean = gufi.replace(/^urn:uuid:/i, '');
    return this.plans.get(clean);
  }

  /**
   * Updates an existing flight plan.
   */
  updatePlan(gufi: string, updated: FficeFlightPlan): FficeFlightPlan {
    const clean = gufi.replace(/^urn:uuid:/i, '');
    if (!this.plans.has(clean)) {
      throw new Error(`Flight plan with GUFI "${gufi}" not found.`);
    }

    const validation = validateFficeFlightPlan(updated);
    if (!validation.isValid) {
      throw new Error(`Update rejected: ${validation.issues.map(i => i.message).join('; ')}`);
    }

    this.plans.set(clean, updated);
    return updated;
  }

  /**
   * Cancels a flight plan.
   */
  cancelPlan(gufi: string): FficeFlightPlan {
    const plan = this.getPlan(gufi);
    if (!plan) {
      throw new Error(`Flight plan with GUFI "${gufi}" not found.`);
    }

    plan.status = 'CANCELLED';
    plan.messageType = 'CANCELLATION';
    return plan;
  }

  /**
   * Lists flight plans with optional filtering.
   */
  listPlans(filter: PlanListFilter = {}): FficeFlightPlan[] {
    let result = Array.from(this.plans.values());

    if (filter.callsign) {
      const cs = filter.callsign.toUpperCase();
      result = result.filter(p => p.flightIdentification.aircraftIdentification.toUpperCase().includes(cs));
    }
    if (filter.departure) {
      const dep = filter.departure.toUpperCase();
      result = result.filter(p => p.departure.aerodrome.toUpperCase() === dep);
    }
    if (filter.arrival) {
      const arr = filter.arrival.toUpperCase();
      result = result.filter(p => p.arrival.aerodrome.toUpperCase() === arr);
    }
    if (filter.status) {
      const st = filter.status.toUpperCase();
      result = result.filter(p => p.status.toUpperCase() === st);
    }

    return result;
  }
}

