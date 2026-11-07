/**
 * FIXM v4.2+ XML and JSON Serializers for FF-ICE Flight Plans
 */
import { FficeFlightPlan } from './types.js';
import { formatDms } from '../geo/coordinates.js';
import { formatGufiUrn } from './gufi.js';

/**
 * Serializes an FF-ICE flight plan to standard FIXM v4.2+ XML.
 */
export function serializeToFixmXml(plan: FficeFlightPlan): string {
  const gufiUrn = formatGufiUrn(plan.gufi);

  const trajectoryPointsXml = plan.trajectory.points4D.map(p => {
    const dms = formatDms(p.coordinates);
    return `        <fx:point4D>
          <fx:pointType>${p.pointType}</fx:pointType>
          <fx:pointIdentifier>${escapeXml(p.identifier)}</fx:pointIdentifier>
          <fx:position>
            <fb:pos>${p.coordinates.latitude.toFixed(6)} ${p.coordinates.longitude.toFixed(6)}</fb:pos>
            <fb:dmsLatitude>${dms.latitude}</fb:dmsLatitude>
            <fb:dmsLongitude>${dms.longitude}</fb:dmsLongitude>
          </fx:position>
          <fx:level>
            <fb:altitude uom="FT">${p.altitudeFeet}</fb:altitude>
            <fb:flightLevel>F${String(p.flightLevel).padStart(3, '0')}</fb:flightLevel>
          </fx:level>
          <fx:time>
            <fb:estimatedTime>${p.estimatedTimestamp}</fb:estimatedTime>
            <fb:elapsedSeconds>${p.cumulativeTimeSeconds}</fb:elapsedSeconds>
          </fx:time>
          <fx:speed>
            <fb:groundSpeed uom="KT">${p.groundSpeedKnots}</fb:groundSpeed>
          </fx:speed>
          <fx:cumulativeDistance uom="NM">${p.cumulativeDistanceNm}</fx:cumulativeDistance>
          <fx:pointSource>${p.pointSource}</fx:pointSource>
          ${p.associatedAirspace ? `<fx:airspace>${escapeXml(p.associatedAirspace)}</fx:airspace>` : ''}
        </fx:point4D>`;
  }).join('\n');

  const crossingsXml = plan.enRoute.airspaceCrossings.map(c => {
    return `      <fx:airspaceCrossing>
        <fx:airspaceDesignator>${escapeXml(c.enteringAirspace)}</fx:airspaceDesignator>
        <fx:crossingLevel>F${String(c.flightLevel).padStart(3, '0')}</fx:crossingLevel>
        <fx:crossingTime>${c.timestamp}</fx:crossingTime>
        <fx:distanceFromStart uom="NM">${c.distanceFromStartNm}</fx:distanceFromStart>
      </fx:airspaceCrossing>`;
  }).join('\n');

  return `<?xml version="1.0" encoding="UTF-8"?>
<fx:Flight xmlns:fx="http://www.fixm.aero/flight/4.2"
           xmlns:fb="http://www.fixm.aero/base/4.2"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           xsi:schemaLocation="http://www.fixm.aero/flight/4.2 FIXM_Core.xsd">
  <fx:gufi codeSpace="urn:uuid">${gufiUrn}</fx:gufi>
  <fx:flightStatus>${plan.status}</fx:flightStatus>
  <fx:messageType>${plan.messageType}</fx:messageType>
  <fx:filingTime>${plan.filingTime}</fx:filingTime>

  <fx:flightIdentification>
    <fx:aircraftIdentification>${escapeXml(plan.flightIdentification.aircraftIdentification)}</fx:aircraftIdentification>
    ${plan.flightIdentification.aircraftRegistration ? `<fx:aircraftRegistration>${escapeXml(plan.flightIdentification.aircraftRegistration)}</fx:aircraftRegistration>` : ''}
  </fx:flightIdentification>

  <fx:aircraft>
    <fx:aircraftType>${escapeXml(plan.aircraft.aircraftType)}</fx:aircraftType>
    <fx:wakeTurbulenceCategory>${plan.aircraft.wakeTurbulence}</fx:wakeTurbulenceCategory>
    <fx:capabilities>
      <fx:standardEquipment>${escapeXml(plan.aircraft.capabilities.standardEquipment)}</fx:standardEquipment>
      <fx:navigationCapabilities>${plan.aircraft.capabilities.navigation.map(escapeXml).join(' ')}</fx:navigationCapabilities>
      <fx:communicationCapabilities>${plan.aircraft.capabilities.communication.map(escapeXml).join(' ')}</fx:communicationCapabilities>
      <fx:surveillanceCapabilities>${plan.aircraft.capabilities.surveillance.map(escapeXml).join(' ')}</fx:surveillanceCapabilities>
    </fx:capabilities>
  </fx:aircraft>

  <fx:departure>
    <fx:aerodrome>${escapeXml(plan.departure.aerodrome)}</fx:aerodrome>
    ${plan.departure.runway ? `<fx:runway>${escapeXml(plan.departure.runway)}</fx:runway>` : ''}
    <fx:elevation uom="FT">${plan.departure.elevationFeet}</fx:elevation>
    <fx:estimatedOffBlockTime>${plan.departure.estimatedOffBlockTime}</fx:estimatedOffBlockTime>
  </fx:departure>

  <fx:arrival>
    <fx:aerodrome>${escapeXml(plan.arrival.aerodrome)}</fx:aerodrome>
    ${plan.arrival.runway ? `<fx:runway>${escapeXml(plan.arrival.runway)}</fx:runway>` : ''}
    <fx:elevation uom="FT">${plan.arrival.elevationFeet}</fx:elevation>
    <fx:estimatedTimeOfArrival>${plan.arrival.estimatedTimeOfArrival}</fx:estimatedTimeOfArrival>
  </fx:arrival>

  <fx:enRoute>
    <fx:cruisingLevel>${plan.enRoute.cruisingLevel}</fx:cruisingLevel>
    <fx:cruisingSpeed uom="KT">${plan.enRoute.cruisingSpeed}</fx:cruisingSpeed>
    <fx:routeString>${escapeXml(plan.enRoute.routeString)}</fx:routeString>
    <fx:airspaceCrossings>
${crossingsXml}
    </fx:airspaceCrossings>
  </fx:enRoute>

  <fx:routeTrajectory>
    <fx:trajectoryProfile>
      <fx:totalDistance uom="NM">${plan.trajectory.totalDistanceNm}</fx:totalDistance>
      <fx:totalFlightTimeMinutes>${plan.trajectory.totalFlightTimeMinutes}</fx:totalFlightTimeMinutes>
      <fx:agreedTrajectory>
${trajectoryPointsXml}
      </fx:agreedTrajectory>
    </fx:trajectoryProfile>
  </fx:routeTrajectory>

  ${plan.remarks ? `<fx:remarks>${escapeXml(plan.remarks)}</fx:remarks>` : ''}
</fx:Flight>`;
}

/**
 * Serializes an FF-ICE flight plan to FIXM JSON.
 */
export function serializeToFixmJson(plan: FficeFlightPlan): string {
  return JSON.stringify(plan, null, 2);
}

function escapeXml(str: string): string {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

