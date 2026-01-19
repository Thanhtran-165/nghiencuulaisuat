# Global Data (FRED) Integration Guide

## Overview

VN Bond Lab supports optional integration with FRED (Federal Reserve Economic Data) to fetch US Treasury yields and global market indicators for comparison with Vietnamese bond market data.

## Setup

### 1. Get FRED API Key (Free)

1. Visit https://fred.stlouisfed.org/docs/api/api_key.html
2. Sign up for a free account
3. Request an API key (instant approval)
4. Copy your API key

### 2. Configure Environment Variables

Add to your `.env` file:

```bash
# FRED API Configuration (Optional)
FRED_API_KEY=your_api_key_here
```

### 3. Install Dependencies

```bash
pip install requests
```

## Supported Series

The following FRED series are supported by default:

| Series ID | Description | Use Case |
|-----------|-------------|----------|
| DGS10 | US 10-Year Treasury Constant Maturity Rate | VN vs US 10Y spread |
| DGS2 | US 2-Year Treasury Constant Maturity Rate | VN vs US 2Y spread |
| DGS3MO | US 3-Month Treasury Constant Maturity Rate | Short-term rates comparison |
| VIXCLS | CBOE Volatility Index: VIX | Market volatility indicator |
| SOFR | Secured Overnight Financing Rate | US overnight rate |
| DTWEXBGS | Trade Weighted U.S. Dollar Index: Broad | FX indicator |

## Usage

### Automatic Ingestion

Once configured, FRED data is automatically fetched during daily ingestion:

```bash
python -m app.ingest daily
```

The system will automatically include `fred_global` provider if API key is set.

### Manual Backfill

To fetch historical FRED data:

```bash
python -m app.ingest backfill --start 2020-01-01 --end 2024-12-31 --providers fred_global
```

### Querying Global Data

Get latest global rates:

```python
from app.db.schema import DatabaseManager

db = DatabaseManager("path/to/db.duckdb")
db.connect()

# Get all latest rates
rates = db.get_global_rates(limit=10)

# Get specific series
us_10y = db.get_global_rates(series_id='DGS10', start_date='2024-01-01')
```

## Features

### Spread Calculations

When global data is available, the system automatically computes:

- **vn10y_minus_us10y**: VN 10Y yield minus US 10Y yield
- **vn2y_minus_us2y**: VN 2Y yield minus US 2Y yield
- **slope_diff**: Difference between VN and US yield curve slopes

### Correlation Analysis

- 60-day rolling correlation between VN10Y and US10Y
- Used to detect decoupling scenarios

### Global Rate Shock Alerts

Automatic alerts when:

- US10Y moves > 0.25% in 5 days AND VN stress is rising
- VN-US spread widens by > 0.5% over 5 days

## Data Storage

Global rates are stored in the `global_rates_daily` table:

```sql
CREATE TABLE global_rates_daily (
    date DATE NOT NULL,
    series_id VARCHAR NOT NULL,
    series_name VARCHAR NOT NULL,
    value DOUBLE,
    source VARCHAR NOT NULL,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, series_id, source)
);
```

## Limitations

- **Rate Limits**: FRED API has rate limits (120 requests/min for default key)
- **Data Availability**: Some series may have limited history
- **Weekend/Holiday Gaps**: FRED doesn't provide data on weekends/holidays
- **Optional Feature**: System works fully without FRED data

## Troubleshooting

### API Key Not Working

```bash
# Test API key directly
curl "https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key=YOUR_KEY&file_type=json&limit=1"
```

### No Data Fetched

Check logs:
```bash
tail -f logs/ingest.log | grep -i fred
```

Common issues:
- Invalid API key
- Network connectivity issues
- Rate limiting (wait a few minutes)

### Data Gaps

FRED data may have gaps due to:
- US market holidays
- Weekends
- Series availability (check FRED website for series start dates)

## Disabling Global Data

To disable FRED integration:

1. Remove or comment out `FRED_API_KEY` from `.env`
2. Or simply don't set it (system will auto-detect)

The system will continue to work with VN-only data.

## Advanced Configuration

### Custom Series

To add custom FRED series, edit `app/providers/fred_global.py`:

```python
DEFAULT_SERIES = {
    'DGS10': 'US 10-Year Treasury Constant Maturity Rate',
    # Add your custom series here
    'CUSTOM_SERIES': 'Custom Series Description',
}
```

### Chunk Size for Backfill

Adjust chunk size for backfill (default: 90 days):

```python
provider = FREDGlobalProvider(api_key=key)
data = provider.fetch_range(
    start_date='2020-01-01',
    end_date='2024-12-31',
    chunk_size=60  # Smaller chunks for slower connections
)
```

## Data Provenance

All global rates include:
- `source`: Set to 'FRED'
- `fetched_at`: Timestamp of data retrieval
- `series_id`: FRED series identifier
- `series_name`: Human-readable description

This ensures full traceability of all data sources.
