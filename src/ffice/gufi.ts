/**
 * GUFI (Globally Unique Flight Identifier) Management
 * ICAO Doc 9965 FF-ICE Requirement: GUFI RFC 4122 UUID v4
 */
import { v4 as uuidv4, validate as uuidValidate } from 'uuid';

/**
 * Generates a new GUFI in standard UUID format.
 */
export function generateGufi(): string {
  return uuidv4();
}

/**
 * Validates whether a string is a syntactically valid GUFI.
 */
export function isValidGufi(gufi: string): boolean {
  if (!gufi) return false;
  const clean = gufi.replace(/^urn:uuid:/i, '');
  return uuidValidate(clean);
}

/**
 * Formats a GUFI as an official ICAO URN.
 * e.g. "urn:uuid:6c84fb90-12c4-11e1-840d-7b25c5ee775a"
 */
export function formatGufiUrn(gufi: string): string {
  const clean = gufi.replace(/^urn:uuid:/i, '');
  return `urn:uuid:${clean}`;
}

