"""
Run this script from the project root to inspect the actual DB schema.
Usage: python scripts/inspect_schema.py

Requires a valid .env file in the project root.
"""
from sqlalchemy import create_engine, inspect, text
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

engine = create_engine(settings.database_url)

with engine.connect() as conn:
    # Show schemas
    print("\n=== SCHEMAS ===")
    schemas = conn.execute(text("SELECT schema_name FROM information_schema.schemata ORDER BY schema_name")).fetchall()
    for s in schemas:
        print(" ", s[0])

    # Inspect raw tables
    for schema, table in [
        ("raw", "dim_series"),
        ("raw", "fact_economic_observations"),
        ("public_analytics", "mart_inflation"),
        ("public_analytics", "mart_labor_market"),
        ("public_analytics", "mart_gdp"),
        ("public_analytics", "mart_economic_summary"),
    ]:
        print(f"\n=== {schema}.{table} ===")
        try:
            rows = conn.execute(text(
                f"SELECT column_name, data_type, is_nullable "
                f"FROM information_schema.columns "
                f"WHERE table_schema = '{schema}' AND table_name = '{table}' "
                f"ORDER BY ordinal_position"
            )).fetchall()
            for col, dtype, nullable in rows:
                print(f"  {col:<35} {dtype:<20} nullable={nullable}")

            # Show a sample row
            sample = conn.execute(text(f'SELECT * FROM "{schema}"."{table}" LIMIT 1')).fetchone()
            if sample:
                print(f"  --- sample row ---")
                for key, val in zip(sample._fields, sample):
                    print(f"  {key}: {val}")
        except Exception as e:
            print(f"  ERROR: {e}")
