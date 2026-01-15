"""
LinkedIn JD Analyzer - Email Notifier Module
Sends HTML reports via Gmail API (OAuth 2.0) or SMTP with retry logic

OAuth 2.0 사용 시 (권장):
    1. python -m notifier.gmail_oauth --setup  # 최초 인증
    2. 이후 자동으로 OAuth 사용

SMTP 사용 시 (fallback):
    - .env에 SENDER_PASSWORD 설정
"""
import json
import smtplib
import logging
import time
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from functools import wraps

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import EMAIL_CONFIG, TEMPLATES_DIR, STORAGE_CONFIG, DATA_DIR

# Configure logging
logger = logging.getLogger(__name__)


def retry(max_retries: int = 3, delay: float = 2.0, backoff: float = 2.0):
    """
    Decorator for retry logic with exponential backoff

    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay after each retry
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                            f"Retrying in {current_delay:.1f}s..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"All {max_retries + 1} attempts failed. Last error: {e}"
                        )

            raise last_exception
        return wrapper
    return decorator


class EmailSender:
    """
    Email sender for LinkedIn JD analysis reports

    Loads analysis data, generates HTML reports using Jinja2,
    and sends via Gmail API (OAuth 2.0) or SMTP with retry logic

    OAuth 2.0이 설정되어 있으면 자동으로 사용하고,
    그렇지 않으면 SMTP fallback을 사용합니다.
    """

    def __init__(
        self,
        smtp_server: str = None,
        smtp_port: int = None,
        sender_email: str = None,
        sender_password: str = None,
        recipient_email: str = None,
        templates_dir: Path = None,
        analysis_file: Path = None,
        use_oauth: bool = None  # None = auto-detect
    ):
        """
        Initialize EmailSender with configuration

        Args:
            smtp_server: SMTP server address (default: from config)
            smtp_port: SMTP server port (default: from config)
            sender_email: Sender email address (default: from config)
            sender_password: Sender email password/app password (default: from config)
            recipient_email: Recipient email address (default: from config)
            templates_dir: Path to templates directory (default: from config)
            analysis_file: Path to analysis.json file (default: from config)
            use_oauth: True=OAuth only, False=SMTP only, None=auto-detect
        """
        # Email configuration
        self.smtp_server = smtp_server or EMAIL_CONFIG["smtp_server"]
        self.smtp_port = smtp_port or EMAIL_CONFIG["smtp_port"]
        self.sender_email = sender_email or EMAIL_CONFIG["sender_email"]
        self.sender_password = sender_password or EMAIL_CONFIG["sender_password"]
        self.recipient_email = recipient_email or EMAIL_CONFIG["recipient_email"]

        # File paths
        self.templates_dir = templates_dir or TEMPLATES_DIR
        self.analysis_file = analysis_file or STORAGE_CONFIG["analysis_file"]

        # Jinja2 environment
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=True
        )

        # Analysis data storage
        self.analysis_data: Optional[Dict[str, Any]] = None
        self.report_html: Optional[str] = None

        # OAuth settings
        self._use_oauth = use_oauth
        self._gmail_oauth = None
        self._gmail_service = None

        # Determine auth method
        self._init_auth_method()

        logger.info(f"EmailSender initialized (OAuth: {self._use_oauth})")

    def _init_auth_method(self):
        """인증 방식 결정 (OAuth vs SMTP)"""
        if self._use_oauth is False:
            # 명시적으로 SMTP 사용
            logger.info("Using SMTP authentication (explicitly configured)")
            return

        # OAuth 토큰 파일 확인
        token_file = DATA_DIR / "gmail_token.pickle"

        if token_file.exists():
            try:
                from .gmail_oauth import GmailOAuth
                self._gmail_oauth = GmailOAuth()
                self._gmail_service = self._gmail_oauth.get_service()
                self._use_oauth = True
                logger.info("Using Gmail OAuth 2.0 authentication")
                return
            except Exception as e:
                logger.warning(f"OAuth initialization failed: {e}")

        if self._use_oauth is True:
            # OAuth가 필수인데 실패
            raise RuntimeError(
                "OAuth required but not configured. Run:\n"
                "  python -m notifier.gmail_oauth --setup"
            )

        # Auto-detect: SMTP fallback
        self._use_oauth = False
        logger.info("Using SMTP authentication (OAuth not configured)")

    def load_analysis(self) -> Dict[str, Any]:
        """
        Load analysis data from analysis.json

        Returns:
            Dictionary containing analysis results

        Raises:
            FileNotFoundError: If analysis.json doesn't exist
            json.JSONDecodeError: If file is not valid JSON
        """
        logger.info(f"Loading analysis from {self.analysis_file}")

        if not self.analysis_file.exists():
            raise FileNotFoundError(
                f"Analysis file not found: {self.analysis_file}. "
                "Please run the Analyzer agent first."
            )

        with open(self.analysis_file, "r", encoding="utf-8") as f:
            self.analysis_data = json.load(f)

        # Validate required fields
        required_fields = ["analyzed_jobs", "skill_frequency", "insights"]
        for field in required_fields:
            if field not in self.analysis_data:
                logger.warning(f"Missing field in analysis data: {field}")

        job_count = len(self.analysis_data.get("analyzed_jobs", []))
        logger.info(f"Loaded analysis with {job_count} jobs")

        return self.analysis_data

    def _prepare_template_data(self) -> Dict[str, Any]:
        """
        Prepare data for template rendering

        Returns:
            Dictionary with template-ready data
        """
        if not self.analysis_data:
            raise ValueError("No analysis data loaded. Call load_analysis() first.")

        analyzed_jobs = self.analysis_data.get("analyzed_jobs", [])
        skill_frequency = self.analysis_data.get("skill_frequency", {})
        insights = self.analysis_data.get("insights", {})

        # Sort skills by frequency for chart display
        sorted_skills = sorted(
            skill_frequency.items(),
            key=lambda x: x[1],
            reverse=True
        )[:15]  # Top 15 skills

        # Calculate max frequency for percentage scaling
        max_freq = max(skill_frequency.values()) if skill_frequency else 100

        # Prepare skill data with percentages
        skill_chart_data = [
            {
                "name": skill,
                "count": count,
                "percentage": round((count / max_freq) * 100)
            }
            for skill, count in sorted_skills
        ]

        # Report metadata
        report_date = datetime.now().strftime("%Y-%m-%d")
        analyzed_at = self.analysis_data.get(
            "analyzed_at",
            datetime.now().isoformat()
        )

        return {
            "report_date": report_date,
            "analyzed_at": analyzed_at,
            "total_jobs": len(analyzed_jobs),
            "jobs": analyzed_jobs,
            "skill_chart_data": skill_chart_data,
            "insights": insights,
            "top_skills": insights.get("top_skills", []),
            "trending_skills": insights.get("trending_skills", []),
            "recommendation": insights.get("recommendation", ""),
            "year": datetime.now().year
        }

    def create_report(self) -> str:
        """
        Create HTML report using Jinja2 template

        Returns:
            Rendered HTML string

        Raises:
            TemplateNotFound: If report.html template doesn't exist
            ValueError: If analysis data not loaded
        """
        logger.info("Creating HTML report")

        try:
            template = self.jinja_env.get_template("report.html")
        except TemplateNotFound:
            raise TemplateNotFound(
                f"Template 'report.html' not found in {self.templates_dir}"
            )

        template_data = self._prepare_template_data()
        self.report_html = template.render(**template_data)

        logger.info(
            f"Report created: {len(self.report_html)} characters, "
            f"{template_data['total_jobs']} jobs"
        )

        return self.report_html

    def _send_email_oauth(self, subject: str, recipient: str) -> bool:
        """
        Send email via Gmail API (OAuth 2.0)
        
        Args:
            subject: Email subject
            recipient: Recipient email address
            
        Returns:
            True if email sent successfully
        """
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.sender_email
        msg['To'] = recipient
        
        # Attach HTML content
        html_part = MIMEText(self.report_html, 'html', 'utf-8')
        msg.attach(html_part)
        
        # Encode message  
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
        
        # Send via Gmail API
        result = self._gmail_service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()
        
        logger.info(f"Email sent successfully to {recipient} (Message ID: {result['id']})")
        return True

    def _send_email_smtp(self, subject: str, recipient: str) -> bool:
        """
        Send email via SMTP
        
        Args:
            subject: Email subject
            recipient: Recipient email address
            
        Returns:
            True if email sent successfully
        """
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.sender_email
        msg["To"] = recipient

        # Attach HTML content
        html_part = MIMEText(self.report_html, "html", "utf-8")
        msg.attach(html_part)

        # Send via SMTP
        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            server.send_message(msg)

        logger.info(f"Email sent successfully to {recipient}")
        return True

    @retry(max_retries=3, delay=2.0, backoff=2.0)
    def send_email(
        self,
        subject: str = None,
        recipient: str = None
    ) -> bool:
        """
        Send HTML report via Gmail OAuth or SMTP with retry logic

        Args:
            subject: Email subject (default: auto-generated with date)
            recipient: Override recipient email (default: from config)

        Returns:
            True if email sent successfully

        Raises:
            ValueError: If no report HTML available
            smtplib.SMTPException: If email sending fails after retries
        """
        if not self.report_html:
            raise ValueError(
                "No report HTML available. Call create_report() first."
            )

        recipient = recipient or self.recipient_email
        if not recipient:
            raise ValueError("No recipient email configured")

        # Default subject with date
        if not subject:
            today = datetime.now().strftime("%Y-%m-%d")
            subject = f"[Canada Data Jobs] Daily Report - {today}"

        logger.info(f"Sending email to {recipient} via {'OAuth' if self._use_oauth else 'SMTP'}")

        # Choose sending method
        if self._use_oauth:
            return self._send_email_oauth(subject, recipient)
        else:
            return self._send_email_smtp(subject, recipient)

    def save_report(self, output_path: Path = None) -> Path:
        """
        Save HTML report to file for debugging/archiving

        Args:
            output_path: Path to save report (default: data/report_YYYY-MM-DD.html)

        Returns:
            Path where report was saved
        """
        if not self.report_html:
            raise ValueError(
                "No report HTML available. Call create_report() first."
            )

        if not output_path:
            today = datetime.now().strftime("%Y-%m-%d")
            output_path = STORAGE_CONFIG["analysis_file"].parent / f"report_{today}.html"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(self.report_html)

        logger.info(f"Report saved to {output_path}")
        return output_path

    def run(
        self,
        save_report: bool = True,
        send_email: bool = True
    ) -> Dict[str, Any]:
        """
        Run complete email notification process

        Args:
            save_report: Whether to save HTML report to file
            send_email: Whether to send email

        Returns:
            Dictionary with execution results
        """
        logger.info("Starting email notification process")
        result = {
            "status": "started",
            "timestamp": datetime.now().isoformat(),
            "jobs_count": 0,
            "report_saved": False,
            "email_sent": False,
            "errors": []
        }

        try:
            # Step 1: Load analysis data
            self.load_analysis()
            result["jobs_count"] = len(self.analysis_data.get("analyzed_jobs", []))

            # Step 2: Create HTML report
            self.create_report()

            # Step 3: Save report (optional)
            if save_report:
                saved_path = self.save_report()
                result["report_saved"] = True
                result["report_path"] = str(saved_path)

            # Step 4: Send email (optional)
            if send_email:
                self.send_email()
                result["email_sent"] = True

            result["status"] = "completed"
            logger.info("Email notification process completed successfully")

        except FileNotFoundError as e:
            result["status"] = "failed"
            result["errors"].append(f"File not found: {e}")
            logger.error(f"Process failed: {e}")

        except TemplateNotFound as e:
            result["status"] = "failed"
            result["errors"].append(f"Template not found: {e}")
            logger.error(f"Process failed: {e}")

        except smtplib.SMTPException as e:
            result["status"] = "partial"
            result["errors"].append(f"Email sending failed: {e}")
            logger.error(f"Email sending failed after retries: {e}")

        except Exception as e:
            result["status"] = "failed"
            result["errors"].append(str(e))
            logger.error(f"Unexpected error: {e}")

        result["completed_at"] = datetime.now().isoformat()
        return result


def main():
    """Main function for standalone execution"""
    import argparse

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(
        description="Send LinkedIn JD analysis report via email"
    )
    parser.add_argument(
        "--no-send",
        action="store_true",
        help="Generate report but don't send email"
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save report to file"
    )
    parser.add_argument(
        "--recipient",
        type=str,
        help="Override recipient email address"
    )

    args = parser.parse_args()

    sender = EmailSender()

    if args.recipient:
        sender.recipient_email = args.recipient

    result = sender.run(
        save_report=not args.no_save,
        send_email=not args.no_send
    )

    print(f"\nExecution Result:")
    print(f"  Status: {result['status']}")
    print(f"  Jobs processed: {result['jobs_count']}")
    print(f"  Report saved: {result['report_saved']}")
    print(f"  Email sent: {result['email_sent']}")

    if result['errors']:
        print(f"  Errors: {result['errors']}")

    return 0 if result['status'] == 'completed' else 1


if __name__ == "__main__":
    exit(main())
