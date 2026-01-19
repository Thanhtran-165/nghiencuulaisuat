# BondY Stress Model Documentation

## Overview

The BondY Stress Index is a composite indicator (0-100) measuring stress in the Vietnamese government bond market. It combines multiple market indicators into a single score, similar to the VIX for equities.

## Components

The stress index combines five component categories:

### 1. Transmission Score (30% weight)
- **Source**: Transmission analytics module
- **Input**: Pre-computed transmission score (0-100)
- **Interpretation**: Higher transmission = higher stress
- **Rationale**: Captures overall market pressure

### 2. Liquidity Stress (25% weight)
- **Source**: Interbank overnight rate
- **Input**: ON rate z-score over 60-day window
- **Interpretation**: High ON rate = tight liquidity = high stress
- **Rationale**: Liquidity crunch is primary stress indicator

### 3. Curve Slope Stress (20% weight)
- **Source**: Yield curve slope (10Y-2Y)
- **Input**: Slope z-score over 252-day window
- **Interpretation**: Extreme slopes (steep or flat) indicate stress
- **Rationale**: Curve abnormalities signal market dislocation

### 4. Auction Stress (15% weight)
- **Source**: Bid-to-cover ratio
- **Input**: Inverse BTC (2.0 - BTC) z-score
- **Interpretation**: Low BTC = weak demand = high stress
- **Rationale**: Failed auctions are clear stress signals

### 5. Turnover Stress (10% weight)
- **Source**: Secondary trading volume
- **Input**: Negative turnover z-score
- **Interpretation**: Low volume = low participation = high stress
- **Rationale**: Market freeze indicates stress

## Calculation Method

### Step 1: Raw Component Values

For each component, compute raw stress indicator:
```python
transmission = transmission_score (0-100)
liquidity = interbank_on_rate (percent)
curve = slope_10y_2y (percent)
auction = 2.0 - bid_to_cover_ratio
turnover = -secondary_volume_zscore
```

### Step 2: Percentile Rank Normalization

Convert each component to percentile rank (0-100) over rolling window:

```python
percentile = (1 + erf(z_score / sqrt(2))) / 2 * 100
```

- Uses 252 trading day rolling window (~1 year)
- Z-scores winsorized at ±3σ
- Handles missing data gracefully

### Step 3: Weighted Composite

Calculate weighted average:
```python
stress_index = Σ(percentile_i × weight_i)
```

Where weights sum to 1.0 (100%).

### Step 4: Regime Bucket Mapping

Map final score to regime bucket:

| Bucket | Score Range | Description |
|--------|------------|-------------|
| S0 | 0-20 | Very Low Stress |
| S1 | 20-40 | Low Stress |
| S2 | 40-60 | Moderate Stress |
| S3 | 60-80 | High Stress |
| S4 | 80-100 | Very High Stress |

## Usage

### Compute Stress for Single Date

```bash
python -m app.analytics stress --date 2024-12-20
```

### Compute Stress for Date Range

```bash
python -m app.analytics stress-range --start 2024-01-01 --end 2024-12-31
```

### Via API

```bash
# Compute stress for specific date
curl -X POST "http://localhost:8000/api/admin/stress/compute?target_date=2024-12-20"

# Get latest stress
curl "http://localhost:8000/api/stress/latest"

# Get stress timeseries
curl "http://localhost:8000/api/stress/timeseries?start_date=2024-01-01&end_date=2024-12-31"

# Get top drivers
curl "http://localhost:8000/api/stress/drivers?date=2024-12-20"
```

### Automatic Computation

Stress is automatically computed during daily ingestion:

```bash
python -m app.ingest daily
```

## Data Storage

Stress data is stored in `bondy_stress_daily` table:

```sql
CREATE TABLE bondy_stress_daily (
    date DATE NOT NULL UNIQUE,
    stress_index DOUBLE,
    regime_bucket VARCHAR,
    driver_json TEXT,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Top Drivers

The system identifies top 3 stress contributors by analyzing:

1. **Contribution**: How much each component pushes stress away from neutral (50)
2. **Formula**: `(percentile - 50) × weight`
3. **Display**: Shows component name and signed contribution

Example:
```
Top Stress Drivers:
1. Liquidity Stress: +12.5 (major contributor to high stress)
2. Curve Slope Stress: +8.3
3. Auction Stress: -2.1 (slightly reducing stress)
```

## Interpretation Guide

### Score Ranges

- **0-25 (S0-S1)**: Normal market conditions
  - Liquidity is ample
  - Auctions are well-subscribed
  - Yield curve is normal

- **25-50 (S1-S2)**: Elevated stress
  - Some liquidity tightening
  - Auction demand softening
  - Curve steepening or flattening

- **50-75 (S2-S3)**: High stress
  - Significant liquidity crunch
  - Weak auction demand
  - Curve distortions

- **75-100 (S3-S4)**: Crisis conditions
  - Severe liquidity shortage
  - Failed auctions
  - Market breakdown

### Response Strategies

Based on regime bucket:

- **S0-S1**: Monitor only, maintain positions
- **S2**: Increase liquidity, reduce duration
- **S3**: Defensive positioning, limit risk
- **S4**: Risk-off, preserve capital

## Global Comparators (Optional)

When FRED data is available, the system also computes:

### VN vs US Spreads

```python
vn10y_minus_us10y = vn_10y_yield - us_10y_yield
vn2y_minus_us2y = vn_2y_yield - us_2y_yield
slope_diff = (vn_10y - vn_2y) - (us_10y - us_2y)
```

### Rolling Correlation

60-day rolling correlation between VN10Y and US10Y:
- High correlation (>0.8): VN follows US rates
- Low correlation (<0.3): VN decoupling from US
- Negative correlation: Divergent monetary policy

### Global Rate Shock Alerts

Alerts triggered when:

1. **ALERT_GLOBAL_RATE_SHOCK**:
   - US10Y moves > 0.25% in 5 days
   - AND VN stress is rising
   - Indicates external shock transmission

2. **ALERT_SPREAD_WIDENING**:
   - VN-US spread widens > 0.5% over 5 days
   - Indicates VN-specific stress

## Limitations

### Data Requirements

- **Minimum 60 days** of data for liquidity z-scores
- **Minimum 252 days** (~1 year) for accurate percentile ranks
- **Transmission metrics** must be computed first

### Missing Data

- Components with missing data are excluded from calculation
- Weights are re-normalized to sum to 1.0
- Stress index may be null if insufficient data

### Model Assumptions

- **Normal distribution**: Z-score normalization assumes normality
- **Stationarity**: Percentile ranks assume stable statistical properties
- **Linear weights**: Simple weighted average (no complex interactions)

## Validation

### Historical Calibration

Model calibrated against historical stress events:
- 2020 COVID crash (S3-S4)
- 2022 tightening cycle (S2-S3)
- 2023 stability period (S0-S1)

### Backtesting

Test stress index as early warning indicator:
- Predicts auction failures
- Leads yield curve inversions
- Correlates with CDS spreads (if available)

## Troubleshooting

### Stress Index Returns Null

**Causes**:
- Insufficient historical data
- Missing transmission metrics
- No interbank rate data

**Solution**:
```bash
# Run transmission metrics first
python -m app.analytics compute --date 2024-12-20

# Then compute stress
python -m app.analytics stress --date 2024-12-20
```

### Unexpected Stress Values

**Check**:
```bash
# View raw components
curl "http://localhost:8000/api/stress/drivers?date=2024-12-20"

# Inspect transmission metrics
curl "http://localhost:8000/api/transmission/latest"
```

### Regime Jumps

Stress index should evolve smoothly. Sudden jumps indicate:
- Data errors
- Component failures
- Market shocks (legitimate)

## References

- VIX methodology (CBOE)
- Kansas City Financial Stress Index
- RBI Financial Stress Index (India)
- ECB Composite Indicator of Systemic Stress

## Changelog

### Version 1.0 (2024)
- Initial release with 5 components
- Percentile rank normalization
- Regime bucket classification
- Top driver decomposition
- Optional global comparators
