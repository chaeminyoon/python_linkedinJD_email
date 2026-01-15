"""
LinkedIn JD Analyzer - Main Entry Point
캐나다 Data Engineer/Scientist 채용공고 자동 분석 시스템

Usage:
    python main.py                    # 전체 파이프라인 실행
    python main.py --scrape-only      # 스크래핑만 실행
    python main.py --analyze-only     # 분석만 실행
    python main.py --notify-only      # 알림만 실행
    python main.py --status           # 파이프라인 상태 조회
    python main.py --trends           # 트렌드 데이터 조회
"""

import argparse
import logging
import sys
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('linkedin_jd.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def setup_orchestrator():
    """Orchestrator 초기화 및 Agent 등록"""
    from orchestrator import Orchestrator
    from scraper import LinkedInScraper
    from analyzer import JDAnalyzer
    from notifier import EmailSender

    orchestrator = Orchestrator()

    # Agent 등록
    orchestrator.register_agents(
        scraper=LinkedInScraper(),
        analyzer=JDAnalyzer(),
        notifier=EmailSender()
    )

    return orchestrator


def run_full_pipeline():
    """전체 파이프라인 실행"""
    logger.info("=" * 60)
    logger.info("LinkedIn JD Analyzer - Full Pipeline")
    logger.info(f"Started at: {datetime.now().isoformat()}")
    logger.info("=" * 60)

    try:
        orchestrator = setup_orchestrator()
        result = orchestrator.run_pipeline()

        if result.get('success'):
            logger.info("✅ Pipeline completed successfully!")
            logger.info(f"Jobs scraped: {result.get('scraper', {}).get('jobs_found', 0)}")
            logger.info(f"Jobs analyzed: {result.get('analyzer', {}).get('jobs_analyzed', 0)}")
            logger.info(f"Email sent: {result.get('notifier', {}).get('email_sent', False)}")
        else:
            logger.error(f"❌ Pipeline failed: {result.get('error')}")

        return result

    except Exception as e:
        logger.exception(f"Pipeline execution failed: {e}")
        return {'success': False, 'error': str(e)}


def run_scrape_only():
    """스크래핑만 실행"""
    logger.info("Running Scraper Agent only...")

    from scraper import LinkedInScraper

    scraper = LinkedInScraper()
    result = scraper.run()

    logger.info(f"Scraping completed. Jobs found: {result.get('jobs_found', 0)}")
    return result


def run_analyze_only():
    """분석만 실행"""
    logger.info("Running Analyzer Agent only...")

    from analyzer import JDAnalyzer

    analyzer = JDAnalyzer()
    result = analyzer.run()

    logger.info(f"Analysis completed. Jobs analyzed: {result.get('jobs_analyzed', 0)}")
    return result


def run_notify_only():
    """알림만 실행"""
    logger.info("Running Notifier Agent only...")

    from notifier import EmailSender

    notifier = EmailSender()
    result = notifier.run()

    logger.info(f"Notification completed. Email sent: {result.get('email_sent', False)}")
    return result


def show_status():
    """파이프라인 상태 조회"""
    from orchestrator import Orchestrator

    orchestrator = Orchestrator()
    status = orchestrator.get_pipeline_status()

    print("\n" + "=" * 60)
    print("📊 Pipeline Status")
    print("=" * 60)

    # Pipeline state
    pipeline = status.get('pipeline_state', {})
    print(f"\nPipeline Status: {pipeline.get('status', 'unknown')}")
    print(f"Last Updated: {pipeline.get('last_updated', 'N/A')}")

    # Agent states
    print("\n📦 Agent States:")
    for agent, state in status.get('agent_states', {}).items():
        print(f"  - {agent}: {state.get('status', 'unknown')} (Last run: {state.get('last_run', 'N/A')})")

    # Recent errors
    errors = status.get('recent_errors', [])
    if errors:
        print("\n⚠️ Recent Errors:")
        for error in errors[-5:]:
            print(f"  - [{error.get('timestamp')}] {error.get('agent')}: {error.get('error')}")

    # Health check
    health = status.get('health', {})
    print(f"\n💚 Health: {'OK' if health.get('is_healthy') else 'UNHEALTHY'}")

    print("=" * 60 + "\n")
    return status


def show_trends(days: int = 30):
    """트렌드 데이터 조회"""
    from orchestrator import Orchestrator

    orchestrator = Orchestrator()
    trends = orchestrator.get_trend_data(days=days)

    print("\n" + "=" * 60)
    print(f"📈 Skill Trends (Last {days} days)")
    print("=" * 60)

    skill_trends = trends.get('skill_trends', {})
    if skill_trends:
        print("\nTop Skills Trend:")
        for skill, values in list(skill_trends.items())[:10]:
            if values:
                avg = sum(values) / len(values)
                trend = "↑" if len(values) > 1 and values[-1] > values[0] else "↓" if len(values) > 1 and values[-1] < values[0] else "→"
                print(f"  - {skill}: {avg:.1f}% {trend}")

    daily_stats = trends.get('daily_stats', [])
    if daily_stats:
        print(f"\nTotal days tracked: {len(daily_stats)}")
        total_jobs = sum(stat.get('total_jobs', 0) for stat in daily_stats)
        print(f"Total jobs collected: {total_jobs}")

    print("=" * 60 + "\n")
    return trends


def main():
    parser = argparse.ArgumentParser(
        description='LinkedIn JD Analyzer - 캐나다 Data 채용공고 자동 분석 시스템',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                  # 전체 파이프라인 실행
  python main.py --scrape-only    # 스크래핑만 실행
  python main.py --analyze-only   # 분석만 실행 (기존 jobs.json 사용)
  python main.py --notify-only    # 알림만 실행 (기존 analysis.json 사용)
  python main.py --status         # 현재 상태 조회
  python main.py --trends 30      # 30일 트렌드 조회
        """
    )

    parser.add_argument('--scrape-only', action='store_true', help='스크래핑만 실행')
    parser.add_argument('--analyze-only', action='store_true', help='분석만 실행')
    parser.add_argument('--notify-only', action='store_true', help='알림만 실행')
    parser.add_argument('--status', action='store_true', help='파이프라인 상태 조회')
    parser.add_argument('--trends', type=int, nargs='?', const=30, help='트렌드 데이터 조회 (기본: 30일)')

    args = parser.parse_args()

    try:
        if args.status:
            show_status()
        elif args.trends:
            show_trends(args.trends)
        elif args.scrape_only:
            run_scrape_only()
        elif args.analyze_only:
            run_analyze_only()
        elif args.notify_only:
            run_notify_only()
        else:
            run_full_pipeline()

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
