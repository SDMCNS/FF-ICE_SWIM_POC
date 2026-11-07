"""
Central GUFI (Globally Unique Flight Identifier) Registry Service.
==============================================================================
ARCHITECTURAL PLACEHOLDER NOTICE:
In accordance with ICAO Doc 9965 (FF-ICE/R Implementation Manual), flight
plans submitted across disparate airline dispatch systems and ANSPs require a
single, authoritative Globally Unique Flight Identifier (GUFI).

In a production System-Wide Information Management (SWIM) federation, this
function is fulfilled by a global Central Flight Plan Registry (such as
EUROCONTROL Network Manager in Europe or FAA System Command Center in the US).

This service acts as the SWIM Central Registry Demonstration Node:
  - Centrally coordinates and allocates RFC 4122 UUID v4 GUFIs.
  - Prevents GUFI collisions when multiple clients submit plans concurrently.
  - Tracks issuing authority, allocation timestamps, and commitment state.
  - Validates GUFIs prior to formal flight plan filing.
==============================================================================
"""
import uuid
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

_LOCK = threading.RLock()

# Central registry in-memory store (keyed by GUFI string)
_CENTRAL_GUFI_REGISTRY: Dict[str, Dict[str, Any]] = {}

ISSUING_AUTHORITY = "SWIM-CENTRAL-REGISTRY-EUR-DEMO"
CENTRAL_REGISTRY_URN = "urn:swim:authority:icao-doc9965:central-registry"

def allocate_central_gufi(
    callsign: str,
    departure_icao: str,
    arrival_icao: str,
    eobt: Optional[str] = None,
    client_id: Optional[str] = "SWIM-CLIENT-DISPATCH",
    originating_ansp: str = "IAA/NATS"
) -> Dict[str, Any]:
    """
    Allocates an authoritative Globally Unique Flight Identifier (GUFI)
    coordinated through the central registry to prevent cross-client collision.
    """
    with _LOCK:
        # Generate RFC 4122 UUID v4
        raw_uuid = str(uuid.uuid4()).lower()
        gufi = f"urn:uuid:{raw_uuid}"
        now_iso = datetime.now(timezone.utc).isoformat() + "Z"

        record = {
            "gufi": gufi,
            "rawUuid": raw_uuid,
            "codeSpace": "urn:uuid",
            "issuingAuthority": ISSUING_AUTHORITY,
            "centralRegistryUrn": CENTRAL_REGISTRY_URN,
            "status": "ALLOCATED", # ALLOCATED -> COMMITTED -> CANCELLED
            "allocatedAt": now_iso,
            "callsign": (callsign or "UNTITLED").strip().upper(),
            "departureIcao": (departure_icao or "").strip().upper(),
            "arrivalIcao": (arrival_icao or "").strip().upper(),
            "eobt": eobt,
            "clientId": client_id,
            "originatingAnsp": originating_ansp,
            "isCentralPlaceholder": True,
            "disclaimer": (
                "Authoritative GUFI allocated by the SWIM Central Registry Demonstration Node. "
                "Placeholder for the ICAO Doc 9965 Global Central Flight Plan Registry."
            )
        }

        _CENTRAL_GUFI_REGISTRY[gufi] = record
        return record

def verify_central_gufi(gufi: str) -> Dict[str, Any]:
    """
    Verifies whether a GUFI is registered with the central registry authority.
    """
    with _LOCK:
        clean = (gufi or "").strip()
        # Normalise urn:uuid: prefix if needed
        if not clean.startswith("urn:uuid:"):
            clean = f"urn:uuid:{clean}"

        record = _CENTRAL_GUFI_REGISTRY.get(clean)
        if record:
            return {
                "isValid": True,
                "isRegistered": True,
                "gufi": clean,
                "record": record,
                "issuingAuthority": record.get("issuingAuthority", ISSUING_AUTHORITY)
            }
        else:
            return {
                "isValid": False,
                "isRegistered": False,
                "gufi": clean,
                "error": "GUFI not found in Central Registry. Plan must obtain a central allocation prior to filing.",
                "issuingAuthority": ISSUING_AUTHORITY
            }

def commit_central_gufi(gufi: str, plan_metadata: Optional[Dict[str, Any]] = None) -> bool:
    """
    Marks an allocated GUFI as COMMITTED upon successful flight plan filing.
    """
    with _LOCK:
        clean = (gufi or "").strip()
        if not clean.startswith("urn:uuid:"):
            clean = f"urn:uuid:{clean}"

        if clean not in _CENTRAL_GUFI_REGISTRY:
            # Self-register if plan was filed with an external GUFI
            _CENTRAL_GUFI_REGISTRY[clean] = {
                "gufi": clean,
                "rawUuid": clean.replace("urn:uuid:", ""),
                "codeSpace": "urn:uuid",
                "issuingAuthority": ISSUING_AUTHORITY,
                "centralRegistryUrn": CENTRAL_REGISTRY_URN,
                "status": "COMMITTED",
                "allocatedAt": datetime.now(timezone.utc).isoformat() + "Z",
                "isCentralPlaceholder": True
            }

        rec = _CENTRAL_GUFI_REGISTRY[clean]
        rec["status"] = "COMMITTED"
        rec["committedAt"] = datetime.now(timezone.utc).isoformat() + "Z"
        if plan_metadata:
            rec.update({k: v for k, v in plan_metadata.items() if k not in ["gufi"]})
        return True

def release_central_gufi(gufi: str, reason: str = "CANCELLED") -> bool:
    """
    Marks a GUFI as CANCELLED/RELEASED in the central registry.
    """
    with _LOCK:
        clean = (gufi or "").strip()
        if not clean.startswith("urn:uuid:"):
            clean = f"urn:uuid:{clean}"

        if clean in _CENTRAL_GUFI_REGISTRY:
            _CENTRAL_GUFI_REGISTRY[clean]["status"] = reason
            _CENTRAL_GUFI_REGISTRY[clean]["releasedAt"] = datetime.now(timezone.utc).isoformat() + "Z"
            return True
        return False

def list_central_gufis(limit: int = 100) -> List[Dict[str, Any]]:
    """Returns list of centrally tracked GUFIs."""
    with _LOCK:
        return list(_CENTRAL_GUFI_REGISTRY.values())[:limit]

