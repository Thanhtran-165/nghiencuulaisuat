"""Export functions for bank rate data."""

import os
import pandas as pd
from typing import List, Dict, Any, Optional
from .db import Database
from .utils import logger


class Exporter:
    """Export data from database to various formats."""

    def __init__(self, db: Database):
        """
        Initialize exporter.

        Args:
            db: Database instance
        """
        self.db = db

    def export_latest(self, output_dir: str) -> Dict[str, str]:
        """
        Export latest data from all sources using MERGED views.

        Uses v_latest_observations_merged to return canonical data
        (one record per bank/series/term, selected by priority).

        Args:
            output_dir: Output directory path

        Returns:
            Dictionary with file names and paths
        """
        os.makedirs(output_dir, exist_ok=True)

        files = {}

        # Get latest merged observations (canonical data from all sources, merged by priority)
        deposit_obs = self.db.get_latest_observations_merged()
        loan_obs = [obs for obs in deposit_obs if obs['product_group'] == 'loan']
        deposit_obs = [obs for obs in deposit_obs if obs['product_group'] == 'deposit']

        # Export long format (all deposit observations)
        if deposit_obs:
            long_file = self.export_long_from_observations(deposit_obs, output_dir)
            files['long'] = long_file

        # Export wide deposit format
        if deposit_obs:
            wide_file = self.export_wide_deposit_from_observations(deposit_obs, output_dir)
            files['wide_deposit'] = wide_file

        # Export loan format
        if loan_obs:
            loan_file = self.export_loan_from_observations(loan_obs, output_dir)
            files['loan'] = loan_file

        return files

    def export_long_from_observations(self, observations: List[Dict[str, Any]], output_dir: str) -> str:
        """
        Export observations in long format (1 row/observation).

        Args:
            observations: List of observation dictionaries
            output_dir: Output directory path

        Returns:
            Path to exported file
        """
        if not observations:
            logger.warning("No observations to export")
            return ""

        # Convert to DataFrame
        df = pd.DataFrame(observations)

        # Select and reorder columns
        columns = [
            'bank_name', 'product_group', 'series_code', 'term_label', 'term_months',
            'rate_pct', 'rate_min_pct', 'rate_max_pct', 'raw_value', 'parse_warnings',
            'source_url', 'scraped_at'
        ]
        # Only include columns that exist
        columns = [col for col in columns if col in df.columns]
        df = df[columns]

        # Sort
        df = df.sort_values(['bank_name', 'series_code', 'term_months'])

        # Write to CSV
        output_path = os.path.join(output_dir, 'long.csv')
        df.to_csv(output_path, index=False, encoding='utf-8')

        logger.info(f"Exported {len(df)} records to {output_path}")
        return output_path

    def export_wide_deposit_from_observations(self, observations: List[Dict[str, Any]], output_dir: str) -> str:
        """
        Export deposit observations in wide format (pivot by tenor).

        Args:
            observations: List of observation dictionaries
            output_dir: Output directory path

        Returns:
            Path to exported file
        """
        if not observations:
            logger.warning("No observations to export")
            return ""

        # Filter only deposit records
        observations = [obs for obs in observations if obs.get('product_group') == 'deposit']

        if not observations:
            logger.warning("No deposit observations to export")
            return ""

        # Convert to DataFrame
        df = pd.DataFrame(observations)

        # Pivot by term_months
        pivot_df = df.pivot_table(
            index=['bank_name', 'series_code'],
            columns='term_months',
            values='rate_pct',
            aggfunc='first'
        ).reset_index()

        # Flatten column names
        pivot_df.columns = [f'{col}_month_rate' if isinstance(col, int) else col
                           for col in pivot_df.columns]

        # Sort
        pivot_df = pivot_df.sort_values(['bank_name', 'series_code'])

        # Write to CSV
        output_path = os.path.join(output_dir, 'wide_deposit.csv')
        pivot_df.to_csv(output_path, index=False, encoding='utf-8')

        logger.info(f"Exported wide deposit data to {output_path}")
        return output_path

    def export_loan_from_observations(self, observations: List[Dict[str, Any]], output_dir: str) -> str:
        """
        Export loan observations (1 row/bank/series with min, max).

        Args:
            observations: List of observation dictionaries
            output_dir: Output directory path

        Returns:
            Path to exported file
        """
        if not observations:
            logger.warning("No observations to export")
            return ""

        # Filter only loan records
        observations = [obs for obs in observations if obs.get('product_group') == 'loan']

        if not observations:
            logger.warning("No loan observations to export")
            return ""

        # Convert to DataFrame
        df = pd.DataFrame(observations)

        # Select and reorder columns
        columns = [
            'bank_name', 'series_code', 'rate_min_pct', 'rate_max_pct',
            'raw_value', 'parse_warnings', 'source_url', 'scraped_at'
        ]
        # Only include columns that exist
        columns = [col for col in columns if col in df.columns]
        df = df[columns]

        # Sort
        df = df.sort_values(['bank_name', 'series_code'])

        # Write to CSV
        output_path = os.path.join(output_dir, 'loan.csv')
        df.to_csv(output_path, index=False, encoding='utf-8')

        logger.info(f"Exported {len(df)} loan records to {output_path}")
        return output_path

    def export_latest_raw_all_sources(self, output_dir: str) -> Dict[str, str]:
        """
        Export latest data from all sources WITHOUT merging (for debugging).

        Uses v_latest_observations (per-source) to show all source data
        including duplicates across sources.

        Args:
            output_dir: Output directory path

        Returns:
            Dictionary with file names and paths
        """
        os.makedirs(output_dir, exist_ok=True)

        files = {}

        # Get all source URLs
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT url FROM sources ORDER BY url")
            urls = [row['url'] for row in cursor.fetchall()]

        # Export each source separately
        for url in urls:
            # Get source_id for this URL
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id FROM sources
                    WHERE url = ?
                    ORDER BY scraped_at DESC
                    LIMIT 1
                """, (url,))
                row = cursor.fetchone()
                if not row:
                    continue
                source_id = row['id']

            # Get observations for this source
            observations = self.db.get_observations_by_source(source_id)

            if not observations:
                continue

            # Determine product type and export accordingly
            is_deposit = 'gui-tiet-kiem' in url
            is_loan = 'so-sanh-lai-suat-vay' in url

            # Create safe filename from URL
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.replace('.', '_')
            filename_prefix = f"{domain}"

            if is_deposit:
                # Export deposit data
                deposit_obs = [obs for obs in observations if obs.get('product_group') == 'deposit']
                if deposit_obs:
                    # Long format
                    long_file = self._export_observations_to_csv(
                        deposit_obs,
                        output_dir,
                        f'{filename_prefix}_long.csv'
                    )
                    files[f'{filename_prefix}_long'] = long_file

                    # Wide format
                    wide_file = self._export_wide_deposit_to_csv(
                        deposit_obs,
                        output_dir,
                        f'{filename_prefix}_wide_deposit.csv'
                    )
                    files[f'{filename_prefix}_wide_deposit'] = wide_file

            elif is_loan:
                # Export loan data
                loan_obs = [obs for obs in observations if obs.get('product_group') == 'loan']
                if loan_obs:
                    loan_file = self._export_observations_to_csv(
                        loan_obs,
                        output_dir,
                        f'{filename_prefix}_loan.csv'
                    )
                    files[f'{filename_prefix}_loan'] = loan_file

        return files

    def export_source(self, source_id: int, output_dir: str) -> Dict[str, str]:
        """
        Export data from a specific source.

        Args:
            source_id: Source ID to export
            output_dir: Output directory path

        Returns:
            Dictionary with file names and paths
        """
        os.makedirs(output_dir, exist_ok=True)

        files = {}

        # Get source details
        source = self.db.get_source(source_id)
        if not source:
            logger.error(f"Source {source_id} not found")
            return files

        # Determine if it's deposit or loan based on URL
        url = source['url']
        if 'gui-tiet-kiem' in url:
            # Deposit source
            long_file = self.export_long(source_id, output_dir)
            wide_file = self.export_wide_deposit(source_id, output_dir)
            files['long'] = long_file
            files['wide_deposit'] = wide_file
        elif 'so-sanh-lai-suat-vay' in url:
            # Loan source
            loan_file = self.export_loan(source_id, output_dir)
            files['loan'] = loan_file

        return files

    def export_long(self, source_id: int, output_dir: str) -> str:
        """
        Export data in long format (1 row/observation).

        Args:
            source_id: Source ID
            output_dir: Output directory path

        Returns:
            Path to exported file
        """
        observations = self.db.get_observations_by_source(source_id)

        if not observations:
            logger.warning(f"No observations found for source {source_id}")
            return ""

        # Convert to DataFrame
        df = pd.DataFrame(observations)

        # Select and reorder columns
        columns = [
            'bank_name', 'product_group', 'series_code', 'term_label', 'term_months',
            'rate_pct', 'rate_min_pct', 'rate_max_pct',
            'source_url', 'scraped_at'
        ]
        df = df[columns]

        # Sort
        df = df.sort_values(['bank_name', 'series_code', 'term_months'])

        # Write to CSV
        output_path = os.path.join(output_dir, 'long.csv')
        df.to_csv(output_path, index=False, encoding='utf-8')

        logger.info(f"Exported {len(df)} records to {output_path}")
        return output_path

    def export_wide_deposit(self, source_id: int, output_dir: str) -> str:
        """
        Export deposit data in wide format (pivot by tenor).

        Args:
            source_id: Source ID
            output_dir: Output directory path

        Returns:
            Path to exported file
        """
        observations = self.db.get_observations_by_source(source_id)

        if not observations:
            logger.warning(f"No observations found for source {source_id}")
            return ""

        # Filter only deposit records
        observations = [obs for obs in observations if obs['product_group'] == 'deposit']

        if not observations:
            logger.warning(f"No deposit observations found for source {source_id}")
            return ""

        # Convert to DataFrame
        df = pd.DataFrame(observations)

        # Pivot by term_months
        pivot_df = df.pivot_table(
            index=['bank_name', 'series_code'],
            columns='term_months',
            values='rate_pct',
            aggfunc='first'
        ).reset_index()

        # Flatten column names
        pivot_df.columns = [f'{col}_month_rate' if isinstance(col, int) else col
                           for col in pivot_df.columns]

        # Sort
        pivot_df = pivot_df.sort_values(['bank_name', 'series_code'])

        # Write to CSV
        output_path = os.path.join(output_dir, 'wide_deposit.csv')
        pivot_df.to_csv(output_path, index=False, encoding='utf-8')

        logger.info(f"Exported wide deposit data to {output_path}")
        return output_path

    def export_loan(self, source_id: int, output_dir: str) -> str:
        """
        Export loan data (1 row/bank/series with min, max).

        Args:
            source_id: Source ID
            output_dir: Output directory path

        Returns:
            Path to exported file
        """
        observations = self.db.get_observations_by_source(source_id)

        if not observations:
            logger.warning(f"No observations found for source {source_id}")
            return ""

        # Filter only loan records
        observations = [obs for obs in observations if obs['product_group'] == 'loan']

        if not observations:
            logger.warning(f"No loan observations found for source {source_id}")
            return ""

        # Convert to DataFrame
        df = pd.DataFrame(observations)

        # Select and reorder columns
        columns = [
            'bank_name', 'series_code', 'rate_min_pct', 'rate_max_pct',
            'source_url', 'scraped_at'
        ]
        df = df[columns]

        # Sort
        df = df.sort_values(['bank_name', 'series_code'])

        # Write to CSV
        output_path = os.path.join(output_dir, 'loan.csv')
        df.to_csv(output_path, index=False, encoding='utf-8')

        logger.info(f"Exported {len(df)} loan records to {output_path}")
        return output_path

    def _export_observations_to_csv(
        self,
        observations: List[Dict[str, Any]],
        output_dir: str,
        filename: str
    ) -> str:
        """
        Helper to export observations to CSV with custom filename.

        Args:
            observations: List of observation dictionaries
            output_dir: Output directory path
            filename: Output filename

        Returns:
            Path to exported file
        """
        if not observations:
            logger.warning("No observations to export")
            return ""

        # Convert to DataFrame
        df = pd.DataFrame(observations)

        # Select and reorder columns
        columns = [
            'bank_name', 'product_group', 'series_code', 'term_label', 'term_months',
            'rate_pct', 'rate_min_pct', 'rate_max_pct', 'raw_value', 'parse_warnings',
            'source_url', 'scraped_at'
        ]
        # Only include columns that exist
        columns = [col for col in columns if col in df.columns]
        df = df[columns]

        # Sort
        df = df.sort_values(['bank_name', 'series_code', 'term_months'])

        # Write to CSV
        output_path = os.path.join(output_dir, filename)
        df.to_csv(output_path, index=False, encoding='utf-8')

        logger.info(f"Exported {len(df)} records to {output_path}")
        return output_path

    def _export_wide_deposit_to_csv(
        self,
        observations: List[Dict[str, Any]],
        output_dir: str,
        filename: str
    ) -> str:
        """
        Helper to export deposit observations in wide format with custom filename.

        Args:
            observations: List of observation dictionaries
            output_dir: Output directory path
            filename: Output filename

        Returns:
            Path to exported file
        """
        if not observations:
            logger.warning("No observations to export")
            return ""

        # Filter only deposit records
        observations = [obs for obs in observations if obs.get('product_group') == 'deposit']

        if not observations:
            logger.warning("No deposit observations to export")
            return ""

        # Convert to DataFrame
        df = pd.DataFrame(observations)

        # Pivot by term_months
        pivot_df = df.pivot_table(
            index=['bank_name', 'series_code'],
            columns='term_months',
            values='rate_pct',
            aggfunc='first'
        ).reset_index()

        # Flatten column names
        pivot_df.columns = [f'{col}_month_rate' if isinstance(col, int) else col
                           for col in pivot_df.columns]

        # Sort
        pivot_df = pivot_df.sort_values(['bank_name', 'series_code'])

        # Write to CSV
        output_path = os.path.join(output_dir, filename)
        pivot_df.to_csv(output_path, index=False, encoding='utf-8')

        logger.info(f"Exported wide deposit data to {output_path}")
        return output_path
