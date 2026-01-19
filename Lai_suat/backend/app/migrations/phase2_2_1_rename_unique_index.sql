-- Phase 2.2.1: Rename unique index to reflect per-source-per-day semantics
--
-- Migration: phase2_2_1_rename_unique_index
-- Description: Renames idx_observations_unique_day → idx_observations_unique_source_day
--              to clarify that the index enforces uniqueness per (source, day)
--
-- This migration is idempotent:
-- - CREATE INDEX IF NOT EXISTS ensures idempotency if new index already exists
-- - DROP INDEX IF EXISTS ensures no error if old index already gone
--
-- Expected: After this migration, only idx_observations_unique_source_day exists
--
-- Run with: python3 -m app.migrations.run_migration phase2_2_1_rename_unique_index.sql

-- Create new index with proper name (idempotent: IF NOT EXISTS)
CREATE UNIQUE INDEX IF NOT EXISTS idx_observations_unique_source_day
ON observations (series_id, bank_id, COALESCE(term_id, -1), observed_day, source_id);

-- Drop old index with unclear name (idempotent: IF EXISTS)
DROP INDEX IF EXISTS idx_observations_unique_day;
