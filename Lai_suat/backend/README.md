# Backend - Interest Rates API

FastAPI backend for serving interest rate data from SQLite database.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment:
Create a `.env` file:
```env
DB_PATH=../data/rates.db
CORS_ORIGINS=http://localhost:3001,http://127.0.0.1:3001
```

3. Ensure database exists:
The database should be at `./data/rates.db` relative to the backend directory.
Copy or symlink your existing `rates.db` to this location.

4. Run the server:
```bash
# From backend directory
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Endpoints

- `GET /health` - Health check
- `GET /meta/latest` - Latest metadata about sources and observations
- `GET /banks` - List all banks
- `GET /series` - List all series
- `GET /latest` - Get latest rates for a series
- `GET /history` - Get historical rates for a bank and series

## Testing

```bash
# Health check
curl http://localhost:8000/health

# Get latest loan rates
curl "http://localhost:8000/latest?series_code=loan_the_chap"

# Get latest deposit rates (12 months)
curl "http://localhost:8000/latest?series_code=deposit_online&term_months=12"

# Get history for a bank
curl "http://localhost:8000/history?bank_name=Vietcombank&series_code=deposit_online&term_months=12"
```
