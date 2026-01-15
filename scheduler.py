"""
LinkedIn JD Analyzer - Scheduler
매일 아침 자동으로 JD 수집 및 분석 실행

Usage:
    python scheduler.py                 # 스케줄러 시작 (기본: 매일 7시)
    python scheduler.py --hour 8        # 매일 8시에 실행
    python scheduler.py --run-now       # 즉시 1회 실행 후 스케줄러 시작
    python scheduler.py --test          # 테스트 모드 (1분마다 실행)
"""

import argparse
import logging
import signal
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import SCHEDULER_CONFIG

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('scheduler.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# APScheduler 로그 레벨 조정
logging.getLogger('apscheduler').setLevel(logging.WARNING)


def run_pipeline_job():
    """스케줄러에서 실행되는 파이프라인 작업"""
    logger.info("=" * 60)
    logger.info(f"🚀 Scheduled job started at {datetime.now().isoformat()}")
    logger.info("=" * 60)

    try:
        from main import run_full_pipeline
        result = run_full_pipeline()

        if result.get('success'):
            logger.info("✅ Scheduled job completed successfully")
        else:
            logger.error(f"❌ Scheduled job failed: {result.get('error')}")

    except Exception as e:
        logger.exception(f"Scheduled job error: {e}")


def create_scheduler(hour: int = None, minute: int = None, timezone: str = None, test_mode: bool = False):
    """스케줄러 생성 및 설정"""
    scheduler = BlockingScheduler()

    if test_mode:
        # 테스트 모드: 1분마다 실행
        scheduler.add_job(
            run_pipeline_job,
            'interval',
            minutes=1,
            id='linkedin_jd_test',
            name='LinkedIn JD Analyzer (Test Mode)',
            max_instances=1
        )
        logger.info("📅 Test mode: Running every 1 minute")
    else:
        # 프로덕션 모드: 매일 지정된 시간에 실행
        hour = hour or SCHEDULER_CONFIG.get('hour', 7)
        minute = minute or SCHEDULER_CONFIG.get('minute', 0)
        timezone = timezone or SCHEDULER_CONFIG.get('timezone', 'America/Toronto')

        trigger = CronTrigger(
            hour=hour,
            minute=minute,
            timezone=timezone
        )

        scheduler.add_job(
            run_pipeline_job,
            trigger=trigger,
            id='linkedin_jd_daily',
            name='LinkedIn JD Analyzer Daily Job',
            max_instances=1,
            replace_existing=True
        )

        logger.info(f"📅 Scheduled to run daily at {hour:02d}:{minute:02d} ({timezone})")

    return scheduler


def signal_handler(signum, frame):
    """Graceful shutdown 처리"""
    logger.info("Received shutdown signal, stopping scheduler...")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description='LinkedIn JD Analyzer Scheduler',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--hour', type=int, help=f'실행 시간 (기본: {SCHEDULER_CONFIG.get("hour", 7)}시)')
    parser.add_argument('--minute', type=int, help=f'실행 분 (기본: {SCHEDULER_CONFIG.get("minute", 0)}분)')
    parser.add_argument('--timezone', type=str, help=f'타임존 (기본: {SCHEDULER_CONFIG.get("timezone", "America/Toronto")})')
    parser.add_argument('--run-now', action='store_true', help='즉시 1회 실행 후 스케줄러 시작')
    parser.add_argument('--test', action='store_true', help='테스트 모드 (1분마다 실행)')

    args = parser.parse_args()

    # Signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("=" * 60)
    logger.info("🗓️  LinkedIn JD Analyzer Scheduler")
    logger.info("=" * 60)

    # 즉시 실행 옵션
    if args.run_now:
        logger.info("Running pipeline immediately...")
        run_pipeline_job()
        logger.info("Immediate run completed. Starting scheduler...")

    # 스케줄러 생성 및 시작
    scheduler = create_scheduler(
        hour=args.hour,
        minute=args.minute,
        timezone=args.timezone,
        test_mode=args.test
    )

    try:
        logger.info("Scheduler started. Press Ctrl+C to stop.")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
