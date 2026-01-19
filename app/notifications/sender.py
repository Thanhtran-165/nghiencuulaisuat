"""
Notification Sender Module

Handles sending notifications via email and webhook.
Safe-by-default: notifications only sent if channels are explicitly configured.
"""
import logging
import smtplib
import json
import httpx
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, List, Optional
from datetime import date

logger = logging.getLogger(__name__)


class NotificationSender:
    """Send notifications via email and webhook"""

    def __init__(self, db_manager):
        """
        Initialize notification sender

        Args:
            db_manager: Database manager instance
        """
        self.db = db_manager

    def get_enabled_channels(self) -> List[Dict[str, Any]]:
        """Get all enabled notification channels from database"""
        try:
            channels = self.db.get_notification_channels(enabled_only=True)
            return channels
        except Exception as e:
            logger.error(f"Error getting notification channels: {e}")
            return []

    def send_alert(
        self,
        alert_code: str,
        alert_data: Dict[str, Any],
        target_date: date
    ) -> Dict[str, Any]:
        """
        Send alert notification to all enabled channels

        Args:
            alert_code: Alert code (e.g., ALERT_LIQUIDITY_SPIKE)
            alert_data: Alert data including message, severity, evidence
            target_date: Date of the alert

        Returns:
            Dictionary with send results per channel
        """
        channels = self.get_enabled_channels()

        if not channels:
            logger.info("No notification channels configured, skipping notification")
            return {
                'status': 'skipped',
                'reason': 'no_channels_configured',
                'channels': []
            }

        results = []

        for channel in channels:
            channel_id = channel['id']
            channel_type = channel['channel_type']

            # Check deduplication - has this alert already been sent to this channel?
            if self.db.has_notification_been_sent(str(target_date), alert_code, channel_id):
                logger.info(f"Alert {alert_code} for {target_date} already sent to channel {channel_id}, skipping")
                results.append({
                    'channel_id': channel_id,
                    'channel_type': channel_type,
                    'status': 'skipped',
                    'reason': 'already_sent'
                })
                continue

            # Parse channel config
            try:
                config = json.loads(channel['config_json']) if channel['config_json'] else {}
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON config for channel {channel_id}: {e}")
                results.append({
                    'channel_id': channel_id,
                    'channel_type': channel_type,
                    'status': 'error',
                    'error': str(e)
                })
                continue

            # Send notification based on channel type
            try:
                if channel_type == 'email':
                    success = self.send_email(alert_code, alert_data, target_date, config)
                    status = 'sent' if success else 'failed'
                    error = None
                elif channel_type == 'webhook':
                    success = self.send_webhook(alert_code, alert_data, target_date, config)
                    status = 'sent' if success else 'failed'
                    error = None
                else:
                    status = 'error'
                    error = f'Unknown channel type: {channel_type}'
                    success = False

                # Record notification event in database
                self.db.insert_notification_event(
                    date=str(target_date),
                    alert_code=alert_code,
                    channel_id=channel_id,
                    status=status,
                    error_message=error
                )

                results.append({
                    'channel_id': channel_id,
                    'channel_type': channel_type,
                    'status': status,
                    'error': error
                })

            except Exception as e:
                logger.error(f"Error sending notification via {channel_type}: {e}")
                self.db.insert_notification_event(
                    date=str(target_date),
                    alert_code=alert_code,
                    channel_id=channel_id,
                    status='error',
                    error_message=str(e)
                )
                results.append({
                    'channel_id': channel_id,
                    'channel_type': channel_type,
                    'status': 'error',
                    'error': str(e)
                })

        return {
            'status': 'completed',
            'channels': results
        }

    def send_email(
        self,
        alert_code: str,
        alert_data: Dict[str, Any],
        target_date: date,
        config: Dict[str, Any]
    ) -> bool:
        """
        Send email notification

        Args:
            alert_code: Alert code
            alert_data: Alert data
            target_date: Date of alert
            config: Email configuration (smtp_server, smtp_port, from_addr, to_addr, username, password)

        Returns:
            True if sent successfully
        """
        try:
            # Extract config
            smtp_server = config.get('smtp_server')
            smtp_port = config.get('smtp_port', 587)
            from_addr = config.get('from_addr')
            to_addr = config.get('to_addr')
            username = config.get('username')
            password = config.get('password')

            # Validate required config
            if not all([smtp_server, from_addr, to_addr]):
                logger.error("Missing required email configuration")
                return False

            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[VN Bond Lab Alert] {alert_code} - {target_date}"
            msg['From'] = from_addr
            msg['To'] = to_addr

            # Create plain text and HTML versions
            severity = alert_data.get('severity', 'UNKNOWN')
            message = alert_data.get('message', 'No message')
            evidence = alert_data.get('evidence', {})

            text_part = self._create_email_text(alert_code, severity, message, evidence, target_date)
            html_part = self._create_email_html(alert_code, severity, message, evidence, target_date)

            msg.attach(MIMEText(text_part, 'plain'))
            msg.attach(MIMEText(html_part, 'html'))

            # Send email
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                if username and password:
                    server.login(username, password)
                server.send_message(msg)

            logger.info(f"Email notification sent for {alert_code} to {to_addr}")
            return True

        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False

    def send_webhook(
        self,
        alert_code: str,
        alert_data: Dict[str, Any],
        target_date: date,
        config: Dict[str, Any]
    ) -> bool:
        """
        Send webhook notification

        Args:
            alert_code: Alert code
            alert_data: Alert data
            target_date: Date of alert
            config: Webhook configuration (url, headers, method)

        Returns:
            True if sent successfully
        """
        try:
            # Extract config
            url = config.get('url')
            headers = config.get('headers', {})
            method = config.get('method', 'POST').upper()

            # Validate required config
            if not url:
                logger.error("Missing webhook URL")
                return False

            # Prepare payload
            payload = {
                'alert_code': alert_code,
                'date': str(target_date),
                'severity': alert_data.get('severity'),
                'message': alert_data.get('message'),
                'evidence': alert_data.get('evidence')
            }

            # Send webhook
            with httpx.Client(timeout=10) as client:
                if method == 'POST':
                    response = client.post(url, json=payload, headers=headers)
                elif method == 'GET':
                    response = client.get(url, params=payload, headers=headers)
                else:
                    logger.error(f"Unsupported webhook method: {method}")
                    return False

                # Raise exception for bad status codes
                response.raise_for_status()

            logger.info(f"Webhook notification sent for {alert_code} to {url}")
            return True

        except httpx.HTTPStatusError as e:
            logger.error(f"Webhook returned error status: {e.response.status_code}")
            return False
        except Exception as e:
            logger.error(f"Error sending webhook: {e}")
            return False

    def _create_email_text(
        self,
        alert_code: str,
        severity: str,
        message: str,
        evidence: Dict[str, Any],
        target_date: date
    ) -> str:
        """Create plain text email body"""
        lines = [
            f"Vietnamese Bond Data Lab - Alert Notification",
            f"",
            f"Alert Code: {alert_code}",
            f"Date: {target_date}",
            f"Severity: {severity}",
            f"",
            f"Message: {message}",
            f"",
            f"Evidence:",
        ]

        for key, value in evidence.items():
            lines.append(f"  {key}: {value}")

        lines.append(f"",
                    f"--",
                    f"This is an automated alert from VN Bond Lab")

        return "\n".join(lines)

    def _create_email_html(
        self,
        alert_code: str,
        severity: str,
        message: str,
        evidence: Dict[str, Any],
        target_date: date
    ) -> str:
        """Create HTML email body"""
        severity_colors = {
            'HIGH': '#dc3545',
            'MEDIUM': '#ffc107',
            'LOW': '#17a2b8'
        }
        color = severity_colors.get(severity, '#6c757d')

        evidence_rows = "\n".join([
            f"<tr><td><strong>{key}</strong></td><td>{value}</td></tr>"
            for key, value in evidence.items()
        ])

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto;">
                <h2 style="color: {color};">Vietnamese Bond Data Lab - Alert</h2>

                <table style="border-collapse: collapse; width: 100%;">
                    <tr style="background-color: #f8f9fa;">
                        <td style="padding: 8px;"><strong>Alert Code:</strong></td>
                        <td style="padding: 8px;"><code>{alert_code}</code></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px;"><strong>Date:</strong></td>
                        <td style="padding: 8px;">{target_date}</td>
                    </tr>
                    <tr style="background-color: #f8f9fa;">
                        <td style="padding: 8px;"><strong>Severity:</strong></td>
                        <td style="padding: 8px;"><span style="color: {color}; font-weight: bold;">{severity}</span></td>
                    </tr>
                </table>

                <h3>Message</h3>
                <p>{message}</p>

                <h3>Evidence</h3>
                <table style="border-collapse: collapse; width: 100%; border: 1px solid #dee2e6;">
                    {evidence_rows}
                </table>

                <hr>
                <p style="color: #6c757d; font-size: 0.9em;">
                    This is an automated alert from VN Bond Lab
                </p>
            </div>
        </body>
        </html>
        """

        return html
