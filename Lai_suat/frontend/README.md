# Frontend - Interest Rates Dashboard

Next.js frontend with a "Liquid Glass" UI for tracking interest rates.

## Setup

1. Install dependencies:
```bash
npm install
```

2. Configure environment:
The `.env.local` file should contain:
```env
NEXT_PUBLIC_API_BASE=http://localhost:8001
```

3. Run the development server:
```bash
npm run dev
```

The application will be available at `http://localhost:3001`

### Dev guardrails (anti “Đang tải…”)
- Dev output is isolated to `.next-dev` (production build uses `.next`), so `npm run build` won’t clobber dev assets.
- `npm run dev` stops any existing `next dev` for this project before starting.
- If anything looks weird: `npm run dev:clean`

## Features

- **Today Dashboard**: View latest deposit and loan rates with KPI cards
- **History**: Track interest rate trends over time with interactive charts
- **Comparison**: Compare online vs. at-counter deposit rates side-by-side
- **Liquid Glass UI**: Modern glassmorphism design with blur effects and transparency

## Build

Create a production build:
```bash
npm run build
```

Start the production server:
```bash
npm start
```

## Components

- `GlassCard`: Glass-effect card component
- `KPIGrid`: Grid of KPI cards
- `DepositTable`: Table for deposit rates
- `LoanTable`: Table for loan rates
- `HistoryChart`: Line/Area chart for historical data
- `TopTabs`: Navigation tabs
