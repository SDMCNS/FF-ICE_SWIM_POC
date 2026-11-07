"""
Database Models and Persistence for FF-ICE Flight Plans and 4D Conflicts.
Uses SQLAlchemy with SQLite persistence.
"""
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    create_engine, Column, String, Integer, Float, DateTime, Text, ForeignKey, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session

Base = declarative_base()

def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class FlightPlanModel(Base):
    """
    Persisted FF-ICE Flight Plan entity in SQLite.
    Stores core metadata, status, EOBT, ETA, and serialized FIXM payloads.
    """
    __tablename__ = "flight_plans"

    gufi = Column(String(64), primary_key=True, index=True) # UUID v4
    callsign = Column(String(16), index=True, nullable=False)
    registration = Column(String(16), nullable=True)
    status = Column(String(20), default="FILED", index=True) # PLANNED, FILED, AGREED, ACTIVE, CANCELLED
    message_type = Column(String(30), default="FILING")      # FILING, MODIFICATION, CANCELLATION, TRIAL_REQUEST
    filing_time = Column(DateTime, default=utc_now)

    departure_icao = Column(String(4), index=True, nullable=False)
    departure_runway = Column(String(8), nullable=True)
    departure_elevation_ft = Column(Integer, default=0)
    eobt = Column(DateTime, index=True, nullable=False) # Off-block / pushback at stand
    etot = Column(DateTime, index=True, nullable=True)  # Estimated Take-Off Time at runway threshold
    taxi_out_minutes = Column(Integer, default=10)      # EXOT

    arrival_icao = Column(String(4), index=True, nullable=False)
    arrival_runway = Column(String(8), nullable=True)
    arrival_elevation_ft = Column(Integer, default=0)
    eta = Column(DateTime, index=True, nullable=False)  # In-block / gate arrival (EIBT)
    eldt = Column(DateTime, index=True, nullable=True) # Estimated Landing Time at runway threshold
    taxi_in_minutes = Column(Integer, default=6)        # EXIT

    aircraft_type = Column(String(8), nullable=False)
    wake_turbulence = Column(String(2), default="M")
    equipment = Column(String(64), default="SDFGIRW/LB1")

    cruising_level = Column(String(8), nullable=False) # e.g. "F280"
    cruising_speed = Column(String(8), default="N0450")
    route_string = Column(Text, nullable=False)

    total_distance_nm = Column(Float, default=0.0)
    total_flight_time_minutes = Column(Float, default=0.0)

    fixm_json = Column(Text, nullable=False)
    fixm_xml = Column(Text, nullable=False)
    remarks = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationship to 4D trajectory points
    trajectory_points = relationship(
        "TrajectoryPointModel",
        back_populates="flight_plan",
        cascade="all, delete-orphan",
        order_by="TrajectoryPointModel.point_index"
    )

class TrajectoryPointModel(Base):
    """
    Individual 4D Trajectory Point for spatial and temporal conflict querying.
    """
    __tablename__ = "trajectory_points"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gufi = Column(String(64), ForeignKey("flight_plans.gufi"), index=True, nullable=False)
    point_index = Column(Integer, nullable=False)
    point_type = Column(String(24), nullable=False) # DEPARTURE, TOC, WAYPOINT, FIR_CROSSING, TOD, DESTINATION
    identifier = Column(String(32), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    altitude_feet = Column(Integer, nullable=False)
    flight_level = Column(Integer, nullable=False)
    cumulative_distance_nm = Column(Float, default=0.0)
    ground_speed_knots = Column(Integer, default=0)
    timestamp = Column(DateTime, index=True, nullable=False)
    airspace = Column(String(32), nullable=True)

    flight_plan = relationship("FlightPlanModel", back_populates="trajectory_points")

    __table_args__ = (
        Index("idx_traj_time_lat_lon", "timestamp", "latitude", "longitude"),
    )

class ConflictRecordModel(Base):
    """
    Logs strategic separation conflicts detected between flight plans.
    """
    __tablename__ = "conflict_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gufi1 = Column(String(64), index=True, nullable=False)
    callsign1 = Column(String(16), nullable=False)
    gufi2 = Column(String(64), index=True, nullable=False)
    callsign2 = Column(String(16), nullable=False)
    conflict_type = Column(String(32), nullable=False) # LATERAL_SEPARATION, VERTICAL_SEPARATION, INTERSECTION
    min_horizontal_separation_nm = Column(Float, nullable=False)
    min_vertical_separation_ft = Column(Integer, nullable=False)
    time_of_closest_approach = Column(DateTime, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    severity = Column(String(16), default="CRITICAL") # CRITICAL, WARNING, ADVISORY
    resolution_advisory = Column(Text, nullable=True)
    detected_at = Column(DateTime, default=utc_now)

def init_db(db_path: str = "ff_ice.db"):
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(engine)

    # Lightweight migration check for added columns on existing SQLite databases
    try:
        with engine.connect() as conn:
            result = conn.exec_driver_sql("PRAGMA table_info(flight_plans);").fetchall()
            existing_cols = {row[1] for row in result}
            if "etot" not in existing_cols:
                conn.exec_driver_sql("ALTER TABLE flight_plans ADD COLUMN etot DATETIME;")
            if "eldt" not in existing_cols:
                conn.exec_driver_sql("ALTER TABLE flight_plans ADD COLUMN eldt DATETIME;")
            if "taxi_out_minutes" not in existing_cols:
                conn.exec_driver_sql("ALTER TABLE flight_plans ADD COLUMN taxi_out_minutes INTEGER DEFAULT 10;")
            if "taxi_in_minutes" not in existing_cols:
                conn.exec_driver_sql("ALTER TABLE flight_plans ADD COLUMN taxi_in_minutes INTEGER DEFAULT 6;")
            conn.commit()
    except Exception as e:
        pass

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal
