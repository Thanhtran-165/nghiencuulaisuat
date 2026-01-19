"""
DEPRECATED (kept for reference)

This module is not wired into the running app. Scheduling in production/local runs
is currently done via:

- `app/main.py` when `SCHEDULER_ENABLED=true` (in-process APScheduler), or
- OS-level schedulers (macOS LaunchAgents / Linux systemd timers) calling
  `python -m app.ingest daily` or `POST /api/admin/ingest/daily`.

Keeping this file avoids breaking older docs, but new code should not depend on it.
"""
import logging
from datetime import time
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Background task scheduler for automation"""

    def __init__(self, db_manager):
        """
        Initialize scheduler

        Args:
            db_manager: Database manager instance
        """
        self.db = db_manager
        self.scheduler: Optional[BackgroundScheduler] = None
        self.jobs = {}

    def start(self, schedule_config: dict = None):
        """
        Start the scheduler with configured jobs

        Args:
            schedule_config: Dictionary with job schedules
                {
                    'daily_pipeline': {'hour': 8, 'minute': 0},  # 8:00 AM daily
                    'weekly_report': {'day_of_week': 'mon', 'hour': 9, 'minute': 0}  # 9:00 AM Monday
                }
        """
        if self.scheduler and self.scheduler.running:
            logger.warning("Scheduler already running")
            return

        self.scheduler = BackgroundScheduler()

        # Add default jobs or custom jobs from config
        if schedule_config is None:
            schedule_config = self._get_default_schedule()

        # Add daily pipeline job
        if 'daily_pipeline' in schedule_config:
            self._add_daily_pipeline_job(schedule_config['daily_pipeline'])

        # Add weekly report job
        if 'weekly_report' in schedule_config:
            self._add_weekly_report_job(schedule_config['weekly_report'])

        self.scheduler.start()
        logger.info("Scheduler started with jobs: %s", list(self.jobs.keys()))

    def stop(self):
        """Stop the scheduler"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    def _get_default_schedule(self) -> dict:
        """Get default job schedules"""
        return {
            'daily_pipeline': {'hour': 8, 'minute': 0},  # 8:00 AM daily
            'weekly_report': {'day_of_week': 'mon', 'hour': 9, 'minute': 0}  # 9:00 AM Monday
        }

    def _add_daily_pipeline_job(self, schedule: dict):
        """Add daily pipeline job"""
        hour = schedule.get('hour', 8)
        minute = schedule.get('minute', 0)

        def run_daily_pipeline():
            """Run daily ingestion and analytics pipeline"""
            try:
                logger.info("Starting scheduled daily pipeline")
                from app.ingest import IngestionPipeline
                from app.analytics.transmission import TransmissionAnalytics

                # Run ingestion
                pipeline = IngestionPipeline(self.db)
                pipeline.run_daily()

                # Compute analytics
                analytics = TransmissionAnalytics(self.db)
                from datetime import date
                analytics.compute_metrics(date.today())

                # Send notifications for any alerts
                alerts = self.db.get_transmission_alerts(
                    start_date=str(date.today()),
                    end_date=str(date.today())
                )

                if alerts:
                    from app.notifications import NotificationSender
                    sender = NotificationSender(self.db)
                    for alert in alerts:
                        sender.send_alert(
                            alert_code=alert['alert_type'],
                            alert_data={
                                'severity': alert['severity'],
                                'message': alert['message'],
                                'evidence': alert.get('evidence', {})
                            },
                            target_date=date.today()
                        )

                logger.info("Scheduled daily pipeline completed successfully")

            except Exception as e:
                logger.error(f"Error in scheduled daily pipeline: {e}")

        job = self.scheduler.add_job(
            run_daily_pipeline,
            trigger=CronTrigger(hour=hour, minute=minute),
            id='daily_pipeline',
            name='Daily Pipeline',
            replace_existing=True
        )

        self.jobs['daily_pipeline'] = job
        logger.info(f"Added daily_pipeline job at {hour:02d}:{minute:02d}")

    def _add_weekly_report_job(self, schedule: dict):
        """Add weekly PDF report job"""
        day_of_week = schedule.get('day_of_week', 'mon')
        hour = schedule.get('hour', 9)
        minute = schedule.get('minute', 0)

        def run_weekly_report():
            """Generate weekly PDF report"""
            try:
                logger.info("Starting scheduled weekly report generation")
                from app.reports.pdf_daily import DailyPDFReportGenerator
                from datetime import date, timedelta

                # Generate report for today
                generator = DailyPDFReportGenerator(self.db)
                report_path = generator.generate_report(date.today())

                logger.info(f"Weekly report generated: {report_path}")

            except Exception as e:
                logger.error(f"Error in scheduled weekly report: {e}")

        job = self.scheduler.add_job(
            run_weekly_report,
            trigger=CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute),
            id='weekly_report',
            name='Weekly Report',
            replace_existing=True
        )

        self.jobs['weekly_report'] = job
        logger.info(f"Added weekly_report job for {day_of_week} at {hour:02d}:{minute:02d}")

    def get_job_status(self) -> dict:
        """Get status of all scheduled jobs"""
        if not self.scheduler:
            return {'status': 'not_started', 'jobs': []}

        return {
            'status': 'running' if self.scheduler.running else 'stopped',
            'jobs': [
                {
                    'id': job.id,
                    'name': job.name,
                    'next_run_time': str(job.next_run_time) if job.next_run_time else None
                }
                for job in self.scheduler.get_jobs()
            ]
        }


# Global scheduler instance
_scheduler_instance = None


def get_scheduler(db_manager):
    """Get or create global scheduler instance"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = TaskScheduler(db_manager)
    return _scheduler_instance
