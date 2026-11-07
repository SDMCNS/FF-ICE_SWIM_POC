/**
 * OpenAPI 3.0 Specification for SWIM-Compliant FF-ICE Information Services (ICAO Doc 10039)
 */

export const SWIM_OPENAPI_SPEC = {
  openapi: '3.0.3',
  info: {
    title: 'SWIM FF-ICE Flight Planning & 4D Trajectory Information Service',
    version: '1.0.0',
    description: 'ICAO Doc 9965 (FF-ICE Release 1) and FIXM v4.2+ compliant System-Wide Information Management (SWIM) flight planning, trajectory advisory, and validation service for UK and Irish airspace.'
  },
  servers: [
    {
      url: '/api/v1',
      description: 'Local SWIM Service Instance'
    }
  ],
  paths: {
    '/ffice/plans': {
      post: {
        summary: 'Submit / File an FF-ICE Flight Plan',
        operationId: 'fileFlightPlan',
        description: 'Accepts an FF-ICE plan in FIXM JSON or XML format, validates it, assigns a GUFI if not present, and stores it.',
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: { $ref: '#/components/schemas/FlightPlan' }
            },
            'application/xml': {
              schema: { type: 'string', example: '<?xml version="1.0"...?><fx:Flight>...</fx:Flight>' }
            }
          }
        },
        responses: {
          '201': {
            description: 'Flight plan filed successfully',
            content: {
              'application/json': { schema: { $ref: '#/components/schemas/FlightPlan' } },
              'application/xml': { schema: { type: 'string' } }
            }
          },
          '400': {
            description: 'Validation failed or malformed plan'
          }
        }
      },
      get: {
        summary: 'List Filed Flight Plans',
        operationId: 'listFlightPlans',
        parameters: [
          { name: 'callsign', in: 'query', schema: { type: 'string' } },
          { name: 'departure', in: 'query', schema: { type: 'string' } },
          { name: 'arrival', in: 'query', schema: { type: 'string' } },
          { name: 'status', in: 'query', schema: { type: 'string' } }
        ],
        responses: {
          '200': {
            description: 'List of flight plans',
            content: {
              'application/json': {
                schema: {
                  type: 'array',
                  items: { $ref: '#/components/schemas/FlightPlan' }
                }
              }
            }
          }
        }
      }
    },
    '/ffice/plans/{gufi}': {
      get: {
        summary: 'Retrieve Flight Plan by GUFI',
        operationId: 'getFlightPlan',
        parameters: [
          { name: 'gufi', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } }
        ],
        responses: {
          '200': {
            description: 'Flight plan details',
            content: {
              'application/json': { schema: { $ref: '#/components/schemas/FlightPlan' } },
              'application/xml': { schema: { type: 'string' } }
            }
          },
          '404': { description: 'Flight plan with specified GUFI not found' }
        }
      },
      put: {
        summary: 'Modify / Update Flight Plan',
        operationId: 'updateFlightPlan',
        parameters: [
          { name: 'gufi', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } }
        ],
        requestBody: {
          required: true,
          content: {
            'application/json': { schema: { $ref: '#/components/schemas/FlightPlan' } }
          }
        },
        responses: {
          '200': { description: 'Flight plan updated' },
          '404': { description: 'Flight plan not found' }
        }
      },
      delete: {
        summary: 'Cancel Flight Plan',
        operationId: 'cancelFlightPlan',
        parameters: [
          { name: 'gufi', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } }
        ],
        responses: {
          '200': { description: 'Flight plan marked CANCELLED' },
          '404': { description: 'Flight plan not found' }
        }
      }
    },
    '/trajectory/calculate': {
      post: {
        summary: 'Calculate 4D Trajectory & Sanity Advisory',
        operationId: 'calculateTrajectory',
        description: 'Computes TOC, TOD, waypoint arrival times, speed, climb/descent profile, and 3D FIR boundary crossings.',
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['departureIcao', 'arrivalIcao', 'aircraftType', 'requestedCruiseFl'],
                properties: {
                  departureIcao: { type: 'string', example: 'EGLL' },
                  departureRunway: { type: 'string', example: '27R' },
                  arrivalIcao: { type: 'string', example: 'EIDW' },
                  arrivalRunway: { type: 'string', example: '28L' },
                  aircraftType: { type: 'string', example: 'A320' },
                  requestedCruiseFl: { type: 'integer', example: 280 },
                  waypointNames: { type: 'array', items: { type: 'string' }, example: ['LIPGO'] },
                  estimatedOffBlockTime: { type: 'string', format: 'date-time' }
                }
              }
            }
          }
        },
        responses: {
          '200': {
            description: 'Calculated 4D trajectory and sanity analysis',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  properties: {
                    totalDistanceNm: { type: 'number' },
                    totalFlightTimeMinutes: { type: 'number' },
                    sanityResult: { type: 'object' },
                    points: { type: 'array', items: { $ref: '#/components/schemas/TrajectoryPoint4D' } },
                    firCrossings: { type: 'array' }
                  }
                }
              }
            }
          }
        }
      }
    },
    '/ffice/validate': {
      post: {
        summary: 'Validate FF-ICE Plan Syntax and Trajectory Feasibility',
        operationId: 'validatePlan',
        requestBody: {
          required: true,
          content: {
            'application/json': { schema: { $ref: '#/components/schemas/FlightPlan' } }
          }
        },
        responses: {
          '200': {
            description: 'Validation report',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  properties: {
                    isValid: { type: 'boolean' },
                    issues: { type: 'array' }
                  }
                }
              }
            }
          }
        }
      }
    },
    '/airports': {
      get: {
        summary: 'Query Aerodromes (UK & Ireland)',
        operationId: 'getAirports',
        parameters: [
          { name: 'query', in: 'query', schema: { type: 'string' } },
          { name: 'country', in: 'query', schema: { type: 'string', enum: ['GB', 'IE'] } }
        ],
        responses: {
          '200': { description: 'Matching airports' }
        }
      }
    },
    '/waypoints': {
      get: {
        summary: 'Query Waypoints (UK & Ireland)',
        operationId: 'getWaypoints',
        parameters: [
          { name: 'query', in: 'query', schema: { type: 'string' } }
        ],
        responses: {
          '200': { description: 'Matching waypoints' }
        }
      }
    },
    '/airspace/fir': {
      get: {
        summary: 'Get UK & Irish 3D FIR Airspaces',
        operationId: 'getFirs',
        responses: {
          '200': { description: 'GeoJSON or list of FIR boundary polygons with altitude bounds' }
        }
      }
    },
    '/aircraft': {
      get: {
        summary: 'Get Aircraft Performance Profiles',
        operationId: 'getAircraft',
        responses: {
          '200': { description: 'List of aircraft models with climb/descent parameters' }
        }
      }
    }
  },
  components: {
    schemas: {
      FlightPlan: {
        type: 'object',
        required: ['gufi', 'status', 'flightIdentification', 'aircraft', 'departure', 'arrival', 'trajectory'],
        properties: {
          gufi: { type: 'string', format: 'uuid' },
          status: { type: 'string', enum: ['PLANNED', 'FILED', 'NEGOTIATING', 'AGREED', 'ACTIVE', 'COMPLETED', 'CANCELLED'] },
          flightIdentification: {
            type: 'object',
            properties: {
              aircraftIdentification: { type: 'string' },
              aircraftRegistration: { type: 'string' }
            }
          },
          aircraft: {
            type: 'object',
            properties: {
              aircraftType: { type: 'string' },
              wakeTurbulence: { type: 'string' },
              capabilities: { type: 'object' }
            }
          },
          departure: {
            type: 'object',
            properties: {
              aerodrome: { type: 'string' },
              runway: { type: 'string' },
              elevationFeet: { type: 'number' },
              estimatedOffBlockTime: { type: 'string' }
            }
          },
          arrival: {
            type: 'object',
            properties: {
              aerodrome: { type: 'string' },
              runway: { type: 'string' },
              elevationFeet: { type: 'number' },
              estimatedTimeOfArrival: { type: 'string' }
            }
          },
          trajectory: {
            type: 'object',
            properties: {
              totalDistanceNm: { type: 'number' },
              totalFlightTimeMinutes: { type: 'number' },
              points4D: { type: 'array' }
            }
          }
        }
      },
      TrajectoryPoint4D: {
        type: 'object',
        properties: {
          pointType: { type: 'string' },
          identifier: { type: 'string' },
          coordinates: {
            type: 'object',
            properties: {
              latitude: { type: 'number' },
              longitude: { type: 'number' }
            }
          },
          altitudeFeet: { type: 'number' },
          flightLevel: { type: 'number' },
          cumulativeDistanceNm: { type: 'number' },
          groundSpeedKnots: { type: 'number' },
          cumulativeTimeSeconds: { type: 'number' },
          estimatedTimestamp: { type: 'string' },
          pointSource: { type: 'string' },
          associatedAirspace: { type: 'string' }
        }
      }
    }
  }
};

