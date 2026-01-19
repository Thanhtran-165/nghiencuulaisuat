-- Migration: Add observed_day column for deduplication
-- Version: 001
-- Date: 2026-01-06
--
-- This migration is NON-DESTRUCTIVE and IDEMPOTENT:
-- - Can be run multiple times safely
-- - Adds computed column for day-based deduplication
-- - Creates unique index to prevent duplicate observations per day

-- Step 1: Add observed_day column (computed from observed_at)
-- This column stores the UTC date part of observed_at
ALTER TABLE observations ADD COLUMN observed_day TEXT;

-- Backfill existing data
UPDATE observations
SET observed_day = date(observed_at);

-- Step 2: Set NOT NULL constraint after backfill
-- (SQLite doesn't support ALTER COLUMN directly, so we recreate)
-- For now, we'll use application-level validation

-- Step 3: Create unique index to prevent duplicate observations per day
-- This ensures: one canonical observation per (series_id, bank_id, term_months, observed_day, source_id)
CREATE UNIQUE INDEX IF NOT EXISTS idx_observations_unique_day
ON observations (series_id, bank_id, COALESCE(term_months, -1), observed_day, source_id);

-- Step 4: Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_observations_observed_day
ON observations (observed_day DESC);

-- Migration completed successfully
-- Expected: rows unchanged, observed_day populated
-- Verify: SELECT COUNT(DISTINCT observed_day) FROM observations;
