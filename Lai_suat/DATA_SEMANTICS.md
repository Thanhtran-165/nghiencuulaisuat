# Data Semantics: Raw vs Canonical Layers

## Overview

The interest rates database uses a **two-layer architecture** to support both:
1. **Raw-all-sources storage**: Preserve all observations from multiple sources
2. **Canonical merged views**: Single source per day with priority selection

This design enables historical analysis while preventing duplicate records in canonical endpoints.

---

## Raw Layer: observations Table

### Schema
```sql
CREATE TABLE observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    bank_id INTEGER NOT NULL,
    series_id INTEGER NOT NULL,
    term_id INTEGER,
    rate_min_pct REAL,
    rate_max_pct REAL,
    rate_pct REAL,
    raw_value TEXT,
    parse_warnings TEXT,
    observed_day TEXT,
    FOREIGN KEY (source_id) REFERENCES sources(id),
    FOREIGN KEY (bank_id) REFERENCES banks(id),
    FOREIGN KEY (series_id) REFERENCES series(id),
    FOREIGN KEY (term_id) REFERENCES terms(id),
    UNIQUE(source_id, bank_id, series_id, term_id)  -- Idempotent per source
);
```

### Unique Index
```sql
CREATE UNIQUE INDEX idx_observations_unique_source_day
ON observations (series_id, bank_id, COALESCE(term_id, -1), observed_day, source_id);
```

**Note**: Prior to v1.2.2.1, this index was named `idx_observations_unique_day`. The rename reflects the correct semantics: unique per (source, day).

**Key**: Includes `source_id` - allows multiple sources to store observations for the same day!

### Semantics
- **ONE ROW PER** `(source_id, series_id, bank_id, term_id, observed_day)`
- Same source cannot have duplicate observations for same day (idempotent)
- **Different sources CAN have observations for same day**
- Example: Timo + 24hmoney can both store rates for VCB 6-month deposit on 2026-01-06

### Use Cases
- Full audit trail of all sources
- Debugging scraping issues
- Source comparison and validation
- `--raw-all-sources` export flag preserves this layer

---

## Canonical Layer: Merged Views

### /latest Canonical: `v_latest_observations_merged`

```sql
CREATE VIEW v_latest_observations_merged AS
SELECT ... FROM (
    SELECT ...,
        ROW_NUMBER() OVER (
            PARTITION BY o.bank_id, o.series_id, o.term_id
            ORDER BY COALESCE(sp.priority, 999) ASC,
                   s.scraped_at DESC,
                   o.id DESC
        ) AS rn
    FROM observations o
    JOIN sources s ON o.source_id = s.id
    LEFT JOIN source_priorities sp ON s.url = sp.url
) ranked_obs
WHERE ranked_obs.rn = 1
```

**Semantics**:
- **ONE ROW PER** `(bank_id, series_id, term_id)` from highest-priority source
- Priority order: `sp.priority ASC` → `scraped_at DESC` → `id DESC`
- Used by `/latest` endpoint

### /history Canonical: Query-Time Dedup

```sql
WITH ranked_obs AS (
    SELECT
        o.observed_day,
        o.rate_pct,
        s.scraped_at,
        ROW_NUMBER() OVER (
            PARTITION BY o.observed_day
            ORDER BY COALESCE(sp.priority, 999) ASC,
                   s.scraped_at DESC,
                   o.id DESC
        ) AS rn
    FROM observations o
    JOIN sources s ON o.source_id = s.id
    LEFT JOIN source_priorities sp ON s.url = sp.url
    WHERE o.bank_id = ? AND o.series_id = ? AND o.term_id = ?
)
SELECT scraped_at, rate_pct, rate_min_pct, rate_max_pct
FROM ranked_obs
WHERE rn = 1 AND observed_day IS NOT NULL
ORDER BY scraped_at ASC
```

**Semantics**:
- **ONE ROW PER** `observed_day` for a given `(bank, series, term)` filter
- Priority order: `sp.priority ASC` → `scraped_at DESC` → `id DESC`
- Returns canonical historical trend with NO duplicate days
- Used by `/history` endpoint

---

## Source Priority

### Priority Table
```sql
CREATE TABLE source_priorities (
    url TEXT NOT NULL PRIMARY KEY,
    priority INTEGER NOT NULL  -- Lower = higher priority
);
```

### Example
```sql
INSERT INTO source_priorities (url, priority) VALUES
    ('https://timo.vn', 1),        -- Highest priority
    ('https://24hmoney.vn', 2),   -- Lower priority
    ('https://eximbank.vn', 3);
```

**Priority Selection Rules**:
1. Lower `priority` value = higher priority (1 is best)
2. If no priority set, defaults to 999 (lowest)
3. Tie-breaker: `scraped_at DESC` (most recent)
4. Final tie-breaker: `id DESC` (latest inserted)

---

## Example Scenario

### Data in Raw Layer
| source_id | bank | series  | term | observed_day | rate_pct |
|-----------|------|---------|------|--------------|----------|
| 1 (timo)  | VCB  | deposit | 6m   | 2026-01-06   | 4.5      |
| 2 (24h)   | VCB  | deposit | 6m   | 2026-01-06   | 4.6      |

**Result**: 2 rows in `observations` table ✅

### /history Canonical Response
```json
GET /history?bank_name=VCB&series_code=deposit_online&term_months=6

{
  "points": [
    {"scraped_at": "2026-01-06T02:00:00Z", "rate_pct": 4.5}  // Only Timo (priority=1)
  ]
}
```

**Result**: 1 point for 2026-01-06 ✅

### /latest Canonical Response
```json
GET /latest?series_code=deposit_online&term_months=12

{
  "rows": [
    {
      "bank_name": "VCB",
      "rate_pct": 4.5,  // From Timo (priority=1 source)
      "source_priority": 1
    }
  ]
}
```

**Result**: 1 row per bank/series/term ✅

---

## --raw-all-sources Flag

When scraping with `--raw-all-sources`, the system:
1. **INSERTS** observations from ALL sources (including duplicates per day)
2. **PRESERVES** raw layer integrity (multiple sources per day)
3. **ALLOWS** canonical endpoints to pick best source via priority

### Export Behavior
```bash
# Raw export (all sources)
python3 -m app.cli scrape --all --raw-all-sources --export /tmp/raw.json
# → Includes ALL observations, multiple per day

# Canonical export (merged)
python3 -m app.cli scrape --all --export /tmp/canonical.json
# → Uses v_latest_observations_merged, 1 per bank/series/term
```

---

## Migration History

### Phase 2 (v1.2.0)
- Added `observed_day` column
- Created `idx_observations_unique_day` with source_id
- Enabled per-day deduplication

### Phase 2.2 (v1.2.2)
- **NO SCHEMA CHANGE** - index already correct!
- Fixed `/history` query to deduplicate by day using priority
- Added comprehensive tests for raw-all-sources semantics
- Documented raw vs canonical layers

### Phase 2.2.1 (v1.2.2.1)
- Renamed unique index `idx_observations_unique_day` → `idx_observations_unique_source_day`
- Migration: `python3 -m app.migrations.run_migration phase2_2_1_rename_unique_index.sql`
- Index name now accurately reflects per-source-per-day semantics

### Phase 2.2.1b (v1.2.2.1b)
- **Standardized migration pipeline**: converted Python script to SQL migration
- Old Python script (`run_phase2_2_1_rename.py`) now deprecated wrapper
- All migrations now run via `run_migration.py` + migrations table tracking

---

## Verification

### Check Unique Index Includes source_id
```bash
python3 -c "import sqlite3; from app.settings import get_settings; conn = sqlite3.connect(get_settings().DB_PATH); cursor = conn.cursor(); cursor.execute('PRAGMA index_info(idx_observations_unique_source_day)'); print(cursor.fetchall())"
# Should return 5 columns, last one is source_id (column index 1)
```

### Test Multi-Source Storage
```bash
# Should show 2 rows if 2 sources scraped same day
sqlite3 data/rates.db "
    SELECT source_id, COUNT(*)
    FROM observations
    WHERE observed_day = '2026-01-06'
    GROUP BY source_id;
"
```

### Test /history Canonical Dedup
```bash
# Should return unique timestamps (no duplicates per day)
curl -s "http://localhost:8001/history?bank_name=VCB&series_code=deposit_online&term_months=6" | \
  jq '.points | length'
```

---

## Summary Table

| Layer | Table/View | Key | Purpose |
|-------|------------|-----|---------|
| **Raw** | `observations` | `(source, bank, series, term, day)` | Store all sources, audit trail |
| **Canonical /latest** | `v_latest_observations_merged` | `(bank, series, term)` + priority | Current rates display |
| **Canonical /history** | Query-time ROW_NUMBER() | `day` + priority | Historical trends |
