"""
FF-ICE Flight Plan Lifecycle Management & Automated Background Sweeper.
Prunes expired, completed, or no-show flight plans according to ICAO ATM & SWIM rules.
Ensures filed plans queries only return upcoming or active in-flight trajectories.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from .database import FlightPlanModel, TrajectoryPointModel

logger = logging.getLogger("ff_ice.lifecycle")

# Operational window constants
# Buffer past ETA (minutes) during which a flight is still considered landing/taxiing in
ETA_BUFFER_MINUTES = 45

# Threshold past EOBT (minutes) after which an unflew/unactivated plan is considered EXPIRED (no-show)
EOBT_EXPIRED_MINUTES = 120


def get_current_utc() -> datetime:
    """Return timezone-naive current UTC datetime for database timestamp comparison."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def determine_operational_status(
    plan: FlightPlanModel,
    now_utc: Optional[datetime] = None,
    buffer_minutes: int = ETA_BUFFER_MINUTES
) -> str:
    """
    Determine the real-time operational status/phase of a flight plan:
    - UPCOMING: EOBT is in the future.
    - IN_FLIGHT: Current time is between EOBT and ETA + buffer (likely airborne or taxiing).
    - COMPLETED: Current time has passed ETA + buffer.
    - EXPIRED: Flight plan EOBT is >2 hours in the past and never progressed.
    - CANCELLED / REJECTED: Terminal administrative statuses.
    """
    if plan.status in ("CANCELLED", "REJECTED", "EXPIRED", "COMPLETED"):
        return plan.status

    if now_utc is None:
        now_utc = get_current_utc()

    # If ETA + buffer has elapsed, the flight is completed
    if plan.eta and (plan.eta + timedelta(minutes=buffer_minutes) < now_utc):
        return "COMPLETED"

    # If EOBT was long in the past (> 2 hours) and never confirmed
    if plan.eobt and (plan.eobt + timedelta(minutes=EOBT_EXPIRED_MINUTES) < now_utc):
        return "EXPIRED"

    # If before departure off-block
    if plan.eobt and now_utc < plan.eobt:
        return "UPCOMING"

    # Otherwise between EOBT and ETA + buffer
    return "IN_FLIGHT"


def is_plan_active(
    plan: FlightPlanModel,
    now_utc: Optional[datetime] = None,
    buffer_minutes: int = ETA_BUFFER_MINUTES
) -> bool:
    """
    Returns True if the flight plan is currently upcoming or likely still in flight.
    Excludes cancelled, expired, and completed flight plans.
    """
    if plan.status in ("CANCELLED", "REJECTED", "EXPIRED", "COMPLETED"):
        return False

    status = determine_operational_status(plan, now_utc, buffer_minutes)
    return status in ("UPCOMING", "IN_FLIGHT")


def sweep_expired_flight_plans(
    db: Session,
    now_utc: Optional[datetime] = None,
    buffer_minutes: int = ETA_BUFFER_MINUTES,
    expired_minutes: int = EOBT_EXPIRED_MINUTES
) -> Dict[str, int]:
    """
    Background check routine that audits and transitions stale flight plans in SQLite:
    - Plans where ETA + buffer has passed -> transitioned to COMPLETED.
    - Plans where EOBT + 120m has passed -> transitioned to EXPIRED.
    Updates database model status, message_type, and serialized fixm_json payload.
    """
    if now_utc is None:
        now_utc = get_current_utc()

    cutoff_completed = now_utc - timedelta(minutes=buffer_minutes)
    cutoff_expired = now_utc - timedelta(minutes=expired_minutes)

    # Only inspect candidate active plans
    candidates = db.query(FlightPlanModel).filter(
        FlightPlanModel.status.in_(["FILED", "AGREED", "ACTIVE"])
    ).all()

    completed_count = 0
    expired_count = 0

    for plan in candidates:
        updated = False
        target_status = None

        if plan.eta and plan.eta < cutoff_completed:
            target_status = "COMPLETED"
            completed_count += 1
            updated = True
        elif plan.eobt and plan.eobt < cutoff_expired and (not plan.eta or plan.eta < now_utc):
            target_status = "EXPIRED"
            expired_count += 1
            updated = True

        if updated and target_status:
            plan.status = target_status
            plan.message_type = target_status
            try:
                data = json.loads(plan.fixm_json)
                data["status"] = target_status
                data["messageType"] = target_status
                data["operationalStatus"] = target_status
                plan.fixm_json = json.dumps(data)
            except Exception as e:
                logger.warning(f"Failed to update fixm_json for GUFI {plan.gufi}: {e}")

    if completed_count > 0 or expired_count > 0:
        try:
            db.commit()
            logger.info(
                f"[Lifecycle Sweeper] Swept stale plans: {completed_count} completed, {expired_count} expired."
            )
        except Exception as e:
            db.rollback()
            logger.error(f"[Lifecycle Sweeper] Database commit error: {e}")

    return {
        "completed": completed_count,
        "expired": expired_count,
        "totalSwept": completed_count + expired_count
    }


async def background_sweeper_loop(
    session_factory,
    stop_event: asyncio.Event,
    interval_seconds: int = 30
):
    """
    Asynchronous continuous background worker task.
    Periodically executes sweep_expired_flight_plans to ensure the database
    and active listings remain free of stale/expired flight plans.
    """
    logger.info(f"[Lifecycle Sweeper] Background sweeper task started (interval: {interval_seconds}s).")
    while not stop_event.is_set():
        try:
            db = session_factory()
            try:
                sweep_expired_flight_plans(db)
            finally:
                db.close()
        except Exception as err:
            logger.error(f"[Lifecycle Sweeper] Error during periodic sweep: {err}")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=float(interval_seconds))
        except asyncio.TimeoutError:
            pass

    logger.info("[Lifecycle Sweeper] Background sweeper task stopped.")
