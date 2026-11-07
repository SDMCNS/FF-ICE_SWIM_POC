"""
Realistic Air Traffic Generator for UK & Irish Airspace.
Populates SQLite database with authentic commercial airline flights connecting major airports.
"""
import os
import sys
import random
import argparse
from datetime import datetime, timedelta, timezone

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ff_ice_server.database import init_db
from ff_ice_server.aero_data import AeroDataStore
from ff_ice_server.generator import generate_realistic_traffic

def generate_traffic(count: int = 20, hours: float = 6.0, db_path: str = "ff_ice.db") -> int:
    engine, SessionLocal = init_db(db_path)
    db = SessionLocal()
    store = AeroDataStore(base_dir=os.path.abspath("."))

    print(f"\n=======================================================")
    print(f"✈️  GENERATING {count} REALISTIC FLIGHTS OVER {hours:.1f} HOURS")
    print(f"🗄️  Target DB: {os.path.abspath(db_path)}")
    print(f"=======================================================\n")

    plans = generate_realistic_traffic(count=count, hours=hours, db=db, store=store)
    for idx, p in enumerate(plans, 1):
        dep = p['departure']['aerodrome']
        arr = p['arrival']['aerodrome']
        cs = p['flightIdentification']['aircraftIdentification']
        ac = p['aircraft']['aircraftType']
        fl = p['enRoute']['cruisingLevel']
        eobt = p['departure']['estimatedOffBlockTime'][11:16]
        print(f"[{idx:02d}/{len(plans)}] {cs:7s} | {dep} -> {arr} | {ac:4s} | {fl} | EOBT {eobt}Z")

    db.close()
    print(f"\n🎉 Successfully generated and persisted {len(plans)} flights in SQLite database!\n")
    return len(plans)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate realistic FF-ICE flight plans for UK/Irish airspace.")
    parser.add_argument("--count", type=int, default=20, help="Number of flight plans to generate (default 20)")
    parser.add_argument("--hours", type=float, default=6.0, help="Time horizon in hours from now (default 6)")
    parser.add_argument("--db", type=str, default="ff_ice.db", help="SQLite database path")
    args = parser.parse_args()

    generate_traffic(count=args.count, hours=args.hours, db_path=args.db)
