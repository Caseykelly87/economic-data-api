-- Schemas and empty mart tables for the containerized smoke test.
--
-- The throwaway Postgres in docker-compose.smoke.yml needs the schemas
-- and tables the macro routes reference so that route queries succeed
-- with an empty result set rather than failing with UndefinedTable.
-- Shapes mirror app/models/economic.py; column lists are kept in sync
-- by hand because this is a smoke-test fixture, not a migration.
--
-- This file is loaded by postgres:16-alpine on first startup via
-- /docker-entrypoint-initdb.d/. It is read-only at runtime.

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS public_analytics;

CREATE TABLE IF NOT EXISTS raw.dim_series (
    series_id   TEXT PRIMARY KEY,
    series_name TEXT NOT NULL,
    source      TEXT
);

CREATE TABLE IF NOT EXISTS raw.fact_economic_observations (
    series_id   TEXT NOT NULL,
    series_name TEXT NOT NULL,
    date        TEXT NOT NULL,
    value       DOUBLE PRECISION,
    source      TEXT,
    PRIMARY KEY (series_id, date)
);

CREATE TABLE IF NOT EXISTS public_analytics.mart_inflation (
    series_id        TEXT NOT NULL,
    observation_date DATE NOT NULL,
    series_name      TEXT NOT NULL,
    value            DOUBLE PRECISION,
    source           TEXT,
    PRIMARY KEY (series_id, observation_date)
);

CREATE TABLE IF NOT EXISTS public_analytics.mart_labor_market (
    series_id        TEXT NOT NULL,
    observation_date DATE NOT NULL,
    series_name      TEXT NOT NULL,
    value            DOUBLE PRECISION,
    source           TEXT,
    PRIMARY KEY (series_id, observation_date)
);

CREATE TABLE IF NOT EXISTS public_analytics.mart_gdp (
    series_id        TEXT NOT NULL,
    observation_date DATE NOT NULL,
    series_name      TEXT NOT NULL,
    value            DOUBLE PRECISION,
    source           TEXT,
    PRIMARY KEY (series_id, observation_date)
);

CREATE TABLE IF NOT EXISTS public_analytics.mart_economic_summary (
    series_id    TEXT PRIMARY KEY,
    series_name  TEXT NOT NULL,
    source       TEXT,
    latest_date  DATE,
    latest_value DOUBLE PRECISION
);
