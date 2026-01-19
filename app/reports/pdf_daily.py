"""
Daily PDF Report Generator for VN Bond Lab

Creates professional PDF reports with:
- Snapshot sections (Vietnamese)
- Charts as images
- Key metrics and alerts
- Provenance and data availability notes
"""
import logging
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    REPORTLAB_AVAILABLE = True
except ImportError:
    logger.warning("ReportLab not installed. PDF generation will be disabled.")
    REPORTLAB_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.font_manager import FontProperties

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    logger.warning("Matplotlib not installed. Chart generation will be disabled.")
    MATPLOTLIB_AVAILABLE = False


class DailyPDFReportGenerator:
    """Generate daily PDF reports for VN bond market"""

    def __init__(self, db_manager, output_dir: str = "data/reports"):
        """
        Initialize PDF generator

        Args:
            db_manager: Database manager instance
            output_dir: Directory to save PDF reports
        """
        self.db = db_manager
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if not REPORTLAB_AVAILABLE:
            logger.error("ReportLab not installed. Cannot generate PDF reports.")
            raise ImportError("ReportLab is required for PDF generation. Install with: pip install reportlab")

        # Set up Vietnamese font support if available
        self._setup_fonts()

    def _setup_fonts(self):
        """Setup font support for Vietnamese characters"""
        try:
            # Try to use system fonts that support Vietnamese
            # Common fonts: Arial, Times New Roman, DejaVuSans
            font_paths = [
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                '/System/Library/Fonts/Helvetica.ttc',
                'C:\\Windows\\Fonts\\arial.ttf'
            ]

            for font_path in font_paths:
                if os.path.exists(font_path):
                    pdfmetrics.registerFont(TTFont('Vietnamese', font_path))
                    logger.info(f"Registered Vietnamese font: {font_path}")
                    return

            logger.warning("No Vietnamese font found, using default fonts")
        except Exception as e:
            logger.warning(f"Font setup failed: {e}")

    def generate_report(
        self,
        target_date: date,
        output_path: Optional[str] = None,
        use_cache: bool = True
    ) -> str:
        """
        Generate daily PDF report

        Args:
            target_date: Date to generate report for
            output_path: Optional output path (default: auto-generated)
            use_cache: If True, check for cached artifact first

        Returns:
            Path to generated PDF file
        """
        logger.info(f"Generating PDF report for {target_date}")

        # Check cache first
        if use_cache:
            cached = self.db.get_report_artifact('daily', str(target_date))
            if cached and cached['status'] == 'completed':
                cached_path = cached['file_path']
                if Path(cached_path).exists():
                    logger.info(f"Using cached PDF: {cached_path}")
                    return cached_path

        if not output_path:
            output_path = self.output_dir / f"daily_{target_date.strftime('%Y%m%d')}.pdf"
        else:
            output_path = Path(output_path)

        # Create PDF document
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )

        # Build report content
        story = []
        styles = getSampleStyleSheet()

        # Add custom styles
        styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a237e'),
            spaceAfter=30,
            alignment=TA_CENTER
        ))

        styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#0d47a1'),
            spaceAfter=12
        ))

        # Generate report sections
        story.extend(self._create_header(target_date, styles))
        story.append(Spacer(1, 0.2*inch))

        # Get snapshot data
        from app.analytics.snapshot import DailySnapshotGenerator
        snapshot_gen = DailySnapshotGenerator(self.db)
        snapshot = snapshot_gen.generate_snapshot(target_date)

        # Add summary section
        story.extend(self._create_summary_section(snapshot, styles))
        story.append(Spacer(1, 0.2*inch))

        # Add comparison section (So với hôm qua)
        story.extend(self._create_comparison_section(snapshot, styles))
        story.append(Spacer(1, 0.2*inch))

        # Add charts
        if MATPLOTLIB_AVAILABLE:
            charts = self._generate_charts(target_date)
            story.extend(self._create_charts_section(charts, styles))
            story.append(Spacer(1, 0.2*inch))

        # Add alerts section
        story.extend(self._create_alerts_section(target_date, styles))
        story.append(Spacer(1, 0.2*inch))

        # Add footer
        story.extend(self._create_footer(styles))

        # Build PDF
        try:
            doc.build(story)
            logger.info(f"PDF report generated: {output_path}")

            # Save artifact to database
            try:
                import os
                file_size = os.path.getsize(output_path)
                self.db.insert_report_artifact(
                    report_type='daily',
                    date=str(target_date),
                    file_path=str(output_path),
                    file_size=file_size,
                    status='completed'
                )
                logger.info(f"PDF artifact saved to database")
            except Exception as e:
                logger.warning(f"Failed to save PDF artifact to database: {e}")

            return str(output_path)
        except Exception as e:
            logger.error(f"Failed to build PDF: {e}")
            # Save failure to database
            try:
                self.db.insert_report_artifact(
                    report_type='daily',
                    date=str(target_date),
                    file_path=str(output_path) if output_path else None,
                    file_size=0,
                    status='failed',
                    error_message=str(e)
                )
            except Exception as db_error:
                logger.warning(f"Failed to save PDF failure to database: {db_error}")
            raise

    def _create_header(self, target_date: date, styles) -> list:
        """Create report header"""
        story = []

        # Title
        title = Paragraph("Vietnamese Bond Market Daily Report", styles['CustomTitle'])
        story.append(title)
        story.append(Spacer(1, 0.1*inch))

        # Date
        date_str = target_date.strftime("%A, %d %B %Y")
        date_para = Paragraph(f"<b>Date:</b> {date_str}", styles['Normal'])
        story.append(date_para)

        return story

    def _create_summary_section(self, snapshot: Dict, styles) -> list:
        """Create summary section from snapshot"""
        story = []

        # Section header
        story.append(Paragraph("Tóm Tắt (Summary)", styles['SectionHeader']))

        # Create summary table
        tom_tat = snapshot.get('tom_tat', {})

        data = [
            ['Metric', 'Value'],
            ['Điểm số Truyền dẫn (Transmission Score)', f"{tom_tat.get('diem_so', 0):.1f}/100"],
            ['Nhóm (Regime Bucket)', tom_tat.get('nhom', 'N/A')],
            ['Lãi suất 10 năm (10Y Yield)', f"{tom_tat.get('lai_suat_10y', 0):.2f}%" if tom_tat.get('lai_suat_10y') else 'N/A'],
            ['Lãi suất qua đêm (ON Rate)', f"{tom_tat.get('lai_suat_qua_dem', 0):.2f}%" if tom_tat.get('lai_suat_qua_dem') else 'N/A'],
        ]

        table = Table(data, colWidths=[3*inch, 2*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))

        story.append(table)
        story.append(Spacer(1, 0.1*inch))

        # Description
        mo_ta = tom_tat.get('mo_ta', '')
        if mo_ta:
            story.append(Paragraph(f"<b>Mô tả:</b> {mo_ta}", styles['Normal']))

        return story

    def _create_comparison_section(self, snapshot: Dict, styles) -> list:
        """Create comparison section (So với hôm qua) from snapshot"""
        story = []

        # Section header
        story.append(Paragraph("So với Hôm Qua (Compared to Baseline)", styles['SectionHeader']))

        # Get baseline date
        baseline_date = snapshot.get('baseline_date')
        if baseline_date:
            story.append(Paragraph(f"<b>Ngày tham chiếu:</b> {baseline_date}", styles['Normal']))
            story.append(Spacer(1, 0.05*inch))

        # Get comparison data
        so_voi = snapshot.get('so_voi_hom_qua', {})
        changes = so_voi.get('changes', {})

        if not changes:
            story.append(Paragraph("Chưa có dữ liệu so sánh", styles['Normal']))
            return story

        # Create comparison table
        data = [['Metric', 'Current', 'Baseline', 'Change', 'Trend']]

        # Score
        if 'diem_so' in changes:
            score = changes['diem_so']
            data.append([
                'Điểm số',
                f"{score.get('hien_tai', 0):.1f}",
                f"{score.get('baseline', 0):.1f}",
                f"{score.get('thay_doi', 0):+.1f}",
                score.get('xu_huong', '-')
            ])

        # 10Y Yield
        if 'lai_suat_10y' in changes:
            yield_10y = changes['lai_suat_10y']
            data.append([
                'Lãi suất 10 năm',
                f"{yield_10y.get('hien_tai', 0):.2f}%",
                f"{yield_10y.get('baseline', 0):.2f}%",
                f"{yield_10y.get('thay_doi', 0):+.2f}%",
                yield_10y.get('xu_huong', '-')
            ])

        # Interbank Rate
        if 'lai_suat_qua_dem' in changes:
            ib = changes['lai_suat_qua_dem']
            data.append([
                'Lãi suất qua đêm',
                f"{ib.get('hien_tai', 0):.2f}%",
                f"{ib.get('baseline', 0):.2f}%",
                f"{ib.get('thay_doi', 0):+.2f}%",
                ib.get('xu_huong', '-')
            ])

        # Curve Slope
        if 'do_cong' in changes:
            slope = changes['do_cong']
            data.append([
                'Độ cong (10Y-2Y)',
                f"{slope.get('hien_tai', 0):.2f}%",
                f"{slope.get('baseline', 0):.2f}%",
                f"{slope.get('thay_doi', 0):+.2f}%",
                slope.get('xu_huong', '-')
            ])

        table = Table(data, colWidths=[2*inch, 1*inch, 1*inch, 1*inch, 1*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))

        story.append(table)

        return story

    def _generate_charts(self, target_date: date) -> Dict[str, str]:
        """Generate charts and save as temporary images"""
        charts = {}

        try:
            # Create temporary directory for charts
            temp_dir = tempfile.mkdtemp()

            # Get historical data for charts
            start_date = target_date - timedelta(days=90)

            # 1. Transmission Score Chart
            stress_data = self.db.get_bondy_stress(
                start_date=str(start_date),
                end_date=str(target_date)
            )

            if stress_data:
                dates = [d['date'] for d in stress_data]
                scores = [d['stress_index'] for d in stress_data]

                plt.figure(figsize=(10, 4))
                plt.plot(dates, scores, color='#ef5350', linewidth=2)
                plt.title('BondY Stress Index (90-Day History)')
                plt.ylabel('Stress Index (0-100)')
                plt.grid(True, alpha=0.3)
                plt.xticks(rotation=45)

                chart_path = os.path.join(temp_dir, 'stress_chart.png')
                plt.savefig(chart_path, dpi=100, bbox_inches='tight')
                plt.close()
                charts['stress'] = chart_path

            # 2. Yield Curve Chart
            yield_data = self.db.get_latest_yield_curve()
            if yield_data:
                tenors = [d['tenor_label'] for d in yield_data]
                yields = [d['spot_rate_annual'] for d in yield_data]

                plt.figure(figsize=(10, 4))
                plt.plot(tenors, yields, marker='o', color='#4fc3f7', linewidth=2)
                plt.title(f'Yield Curve ({target_date})')
                plt.ylabel('Yield (%)')
                plt.grid(True, alpha=0.3)

                chart_path = os.path.join(temp_dir, 'yield_curve_chart.png')
                plt.savefig(chart_path, dpi=100, bbox_inches='tight')
                plt.close()
                charts['yield_curve'] = chart_path

        except Exception as e:
            logger.error(f"Error generating charts: {e}")

        return charts

    def _create_charts_section(self, charts: Dict[str, str], styles) -> list:
        """Create charts section"""
        story = []

        if not charts:
            return story

        story.append(Paragraph("Biểu Đồ (Charts)", styles['SectionHeader']))

        for chart_name, chart_path in charts.items():
            if os.path.exists(chart_path):
                try:
                    img = Image(chart_path, width=6*inch, height=3*inch)
                    story.append(img)
                    story.append(Spacer(1, 0.1*inch))
                except Exception as e:
                    logger.warning(f"Could not add chart {chart_name}: {e}")

        return story

    def _create_alerts_section(self, target_date: date, styles) -> list:
        """Create alerts section"""
        story = []

        story.append(Paragraph("Cảnh Báo (Alerts)", styles['SectionHeader']))

        # Get recent alerts
        start_date = target_date - timedelta(days=7)
        alerts = self.db.get_transmission_alerts(
            start_date=str(start_date),
            end_date=str(target_date),
            limit=20
        )

        if not alerts:
            story.append(Paragraph("Không có cảnh báo nào trong 7 ngày qua.", styles['Normal']))
            return story

        # Create alerts table
        data = [['Date', 'Type', 'Severity', 'Message']]

        for alert in alerts[:10]:  # Top 10 alerts
            data.append([
                alert['date'],
                alert['alert_type'],
                alert['severity'],
                alert['message'][:50] + '...' if len(alert['message']) > 50 else alert['message']
            ])

        table = Table(data, colWidths=[1*inch, 1.5*inch, 1*inch, 2.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))

        story.append(table)

        return story

    def _create_footer(self, styles) -> list:
        """Create report footer with provenance"""
        story = []

        story.append(PageBreak())

        story.append(Paragraph("Ghi Chú (Notes)", styles['SectionHeader']))

        notes = [
            "• This report is automatically generated by VN Bond Lab",
            "• Data sources: HNX, SBV, ABO, FRED (if enabled)",
            "• Transmission score (0-100): Higher values indicate more stress",
            "• Stress index (0-100): Composite measure of market stress",
            "• Missing data: Some datasets may be incomplete",
            "• For questions, contact the data team"
        ]

        for note in notes:
            story.append(Paragraph(note, styles['Normal']))
            story.append(Spacer(1, 0.05*inch))

        # Data availability
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph("<b>Data Availability:</b>", styles['Normal']))

        # Check data availability
        coverage = self._get_data_coverage()

        for table, info in coverage.items():
            status = "✓ Available" if info['has_data'] else "✗ Not available"
            story.append(Paragraph(f"• {table}: {status}", styles['Normal']))

        return story

    def _get_data_coverage(self) -> Dict[str, Dict]:
        """Get data coverage information"""
        tables = [
            'gov_yield_curve',
            'interbank_rates',
            'gov_auction_results',
            'gov_secondary_trading',
            'policy_rates',
            'global_rates_daily'
        ]

        coverage = {}

        for table in tables:
            try:
                sql = f"""
                SELECT COUNT(*) as count, MAX(date) as latest
                FROM {table}
                """

                result = self.db.con.execute(sql).fetchone()

                coverage[table] = {
                    'has_data': result[0] > 0 if result else False,
                    'latest_date': str(result[1]) if result and result[1] else None
                }
            except Exception as e:
                coverage[table] = {
                    'has_data': False,
                    'error': str(e)
                }

        return coverage


def generate_daily_pdf(
    db_manager,
    target_date: date,
    output_dir: str = "data/reports"
) -> Optional[str]:
    """
    Convenience function to generate daily PDF report

    Args:
        db_manager: Database manager instance
        target_date: Date to generate report for
        output_dir: Output directory

    Returns:
        Path to generated PDF or None if failed
    """
    try:
        generator = DailyPDFReportGenerator(db_manager, output_dir)
        return generator.generate_report(target_date)
    except Exception as e:
        logger.error(f"Failed to generate PDF report: {e}")
        return None
