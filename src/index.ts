/**
 * FF-ICE Flight Plan Creation & Consumption Library
 * ICAO Doc 9965 & FIXM v4.2+ Compliant with System-Wide Information Management (SWIM) interfaces
 */

// 1. Geodesy & Spatial Utilities
export * from './geo/coordinates.js';
export * from './geo/distance.js';
export * from './geo/fir-spatial.js';

// 2. Data Ingestion & Store
export * from './data/types.js';
export * from './data/airport-loader.js';
export * from './data/waypoint-loader.js';
export * from './data/route-loader.js';
export * from './data/fir-loader.js';
export * from './data/aero-store.js';

// 3. Performance & Trajectory Engine
export * from './performance/aircraft-database.js';
export * from './performance/sanity-checker.js';
export * from './performance/trajectory-calculator.js';

// 4. FF-ICE & FIXM Domain Model
export * from './ffice/types.js';
export * from './ffice/gufi.js';
export * from './ffice/fixm-serializer.js';
export * from './ffice/fixm-deserializer.js';
export * from './ffice/validator.js';

// 5. SWIM Information Services & Server
export * from './swim/openapi.js';
export * from './swim/swim-service.js';
export * from './swim/server.js';

