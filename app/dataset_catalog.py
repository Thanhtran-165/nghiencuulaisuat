"""
Dataset Catalog CLI
Lists all available datasets with metadata
"""
import sys
import json
from pathlib import Path
from datetime import date

from app.config import settings


# Dataset catalog registry
DATASET_CATALOG = {
    "gov_yield_curve": {
        "name": "Government Bond Yield Curve",
        "description": "Daily yield curve by tenor",
        "provider": "HNX_YC",
        "url": "https://hnx.vn/trai-phieu/duong-cong-loi-suat.html",
        "access_method": "HTML (POST endpoint by date)",
        "supports_historical": True,
        "earliest_known_date": "2014-01-02",
        "accumulation_start": None,
        "provenance": "OFFICIAL",
        "table": "gov_yield_curve",
        "frequency": "Daily"
    },
    "gov_yield_change_stats": {
        "name": "Yield Change Statistics",
        "description": "Daily yield change statistics from HNX FTP",
        "provider": "HNX_FTP_PDF",
        "url": "https://owa.hnx.vn/ftp///THONGKEGIAODICH",
        "access_method": "PDF",
        "supports_historical": True,
        "earliest_known_date": "2013-01-01",
        "accumulation_start": None,
        "provenance": "OFFICIAL",
        "table": "gov_yield_change_stats",
        "frequency": "Daily"
    },
    "interbank_rates": {
        "name": "Interbank Interest Rates",
        "description": "Daily interbank rates by tenor",
        "provider": "SBV",
        "url": "https://www.sbv.gov.vn/webcenter/portal/m/menu/trangchu/ls/lsttlnh",
        "access_method": "HTML",
        "supports_historical": False,
        "earliest_known_date": None,
        "accumulation_start": date.today().isoformat(),
        "provenance": "OFFICIAL",
        "table": "interbank_rates",
        "frequency": "Daily"
    },
    "gov_auction_results": {
        "name": "Government Bond Auction Results",
        "description": "Auction results for T-bills and government bonds",
        "provider": "HNX_AUCTION",
        "url": "https://hnx.vn/trai-phieu/dau-gia-trai-phieu.html",
        "access_method": "HTML/PDF",
        "supports_historical": True,
        "earliest_known_date": "2013-01-01",
        "accumulation_start": None,
        "provenance": "OFFICIAL",
        "table": "gov_auction_results",
        "frequency": "Weekly"
    },
    "secondary_trading": {
        "name": "Secondary Market Trading Statistics",
        "description": "Daily bond trading volume and value",
        "provider": "HNX_TRADING",
        "url": "https://hnx.vn/vi-vn/trai-phieu/ket-qua-gd-trong-ngay.html",
        "access_method": "HTML (POST endpoint by date)",
        "supports_historical": True,
        "earliest_known_date": "2025-01-15",
        "accumulation_start": None,
        "provenance": "OFFICIAL",
        "table": "gov_secondary_trading",
        "frequency": "Daily"
    },
    "policy_rates": {
        "name": "SBV Policy Rates",
        "description": "Central bank policy rates (refinancing, discount, etc.)",
        "provider": "SBV_POLICY",
        "url": "https://www.sbv.gov.vn",
        "access_method": "HTML",
        "supports_historical": False,
        "earliest_known_date": None,
        "accumulation_start": date.today().isoformat(),
        "provenance": "OFFICIAL",
        "table": "policy_rates",
        "frequency": "As announced"
    },
    "bank_rates": {
        "name": "Bank Deposit/Loan Rates",
        "description": "Deposit (online/offline) and loan rates by bank (imported from Lai_suat project)",
        "provider": "LAI_SUAT",
        "url": "local://Lai_suat/data/rates.db",
        "access_method": "Local SQLite import (bridge)",
        "supports_historical": True,
        "earliest_known_date": None,
        "accumulation_start": None,
        "provenance": "THIRD-PARTY",
        "table": "bank_rates",
        "frequency": "Daily (as scraped)"
    }
}


def main():
    """CLI entry point for dataset catalog"""
    import argparse

    parser = argparse.ArgumentParser(description='Vietnamese Bond Data Lab - Dataset Catalog')
    parser.add_argument('--format', choices=['table', 'json'], default='table',
                       help='Output format (default: table)')
    parser.add_argument('--output', help='Output file path (for JSON)')

    args = parser.parse_args()

    if args.format == 'json':
        # Output JSON catalog
        catalog_data = {
            "catalog_date": date.today().isoformat(),
            "datasets": DATASET_CATALOG
        }

        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(catalog_data, f, indent=2)
            print(f"Catalog saved to {output_path}")
        else:
            print(json.dumps(catalog_data, indent=2))

    else:
        # Output table format
        print("\n" + "=" * 120)
        print("VIETNAMESE BOND DATA LAB - DATASET CATALOG")
        print("=" * 120)
        print()

        # Header
        print(f"{'Dataset ID':<25} {'Name':<30} {'Historical':<12} {'Earliest':<12} {'Provider':<15} {'Provenance':<12}")
        print("-" * 120)

        for dataset_id, info in DATASET_CATALOG.items():
            historical = "YES" if info['supports_historical'] else "NO (daily acc.)"
            earliest = info['earliest_known_date'] or (info['accumulation_start'] if info['accumulation_start'] else "N/A")
            provider = info['provider']
            provenance = info['provenance']
            name = info['name'][:28]

            print(f"{dataset_id:<25} {name:<30} {historical:<12} {earliest:<12} {provider:<15} {provenance:<12}")

        print("=" * 120)
        print()
        print("Legend:")
        print("  Historical YES   = Can backfill from earliest_known_date")
        print("  Historical NO    = Daily accumulation only from accumulation_start")
        print("  Provenance OFFICIAL  = Official source")
        print("  Provenance NON-OFFICIAL = Unofficial/validation source")
        print()
        print(f"Total Datasets: {len(DATASET_CATALOG)}")
        print()


if __name__ == '__main__':
    main()
