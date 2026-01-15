"""
LinkedIn JD Analyzer - Full Pipeline Runner
크롤링 -> LLM 분석 -> 이메일 발송 전체 자동화

Usage:
    python run_pipeline.py                    # 전체 파이프라인
    python run_pipeline.py --skip-scrape      # 스크래핑 건너뛰기 (기존 데이터 사용)
    python run_pipeline.py --report-file PATH # 특정 리포트 파일 사용
"""
import os
import sys
import json
import logging
import argparse
import glob
from datetime import datetime
from pathlib import Path

# Setup project path
sys.path.append(str(Path(__file__).resolve().parent))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('pipeline_run.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def get_latest_report_file():
    """가장 최근 리포트 파일 찾기"""
    data_dir = Path(__file__).resolve().parent / "data"
    report_files = list(data_dir.glob("linkedin_report_*.json"))
    
    if not report_files:
        return None
    
    # Sort by modification time (newest first)
    report_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return str(report_files[0])


def run_pipeline(skip_scrape=False, report_file=None):
    """파이프라인 실행"""
    logger.info("="*60)
    logger.info("LinkedIn JD Analyzer - Pipeline")
    logger.info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if skip_scrape:
        logger.info("Mode: Skip Scraping (LLM Analysis + Email only)")
    logger.info("="*60)
    
    results = {
        'scraper': None,
        'analyzer': None,
        'notifier': None,
        'success': False
    }
    
    # ============================================================
    # STEP 1: 스크래핑 (LinkedIn 채용공고 수집)
    # ============================================================
    if not skip_scrape:
        logger.info("\n[STEP 1/3] Starting LinkedIn Scraping...")
        logger.info("Running scraper as subprocess (for better LinkedIn compatibility)...")
        
        try:
            import subprocess
            
            # Run simple_login_access.py as a separate process with --auto flag
            scraper_script = Path(__file__).resolve().parent / "scraper" / "simple_login_access.py"
            
            # Execute and wait for completion (--auto skips the input() wait)
            process = subprocess.run(
                ["python", str(scraper_script), "--auto"],
                cwd=str(Path(__file__).resolve().parent),
                capture_output=False,  # Let user see the browser
                text=True
            )
            
            if process.returncode == 0:
                # Find the latest report file created by the scraper
                report_file = get_latest_report_file()
                
                if report_file:
                    logger.info(f"[OK] Scraping completed. Report: {Path(report_file).name}")
                    results['scraper'] = {'success': True, 'report_file': report_file}
                else:
                    logger.error("[FAIL] Scraping completed but no report file found")
                    results['scraper'] = {'success': False, 'error': 'No report file found'}
                    return results
            else:
                logger.error(f"[FAIL] Scraping failed with exit code: {process.returncode}")
                results['scraper'] = {'success': False, 'error': f'Exit code: {process.returncode}'}
                return results
                
        except Exception as e:
            logger.error(f"[FAIL] Scraping error: {e}")
            results['scraper'] = {'success': False, 'error': str(e)}
            return results
    else:
        logger.info("\n[STEP 1/3] Skipping Scraping (using existing data)...")
        
        # Find report file
        if not report_file:
            report_file = get_latest_report_file()
        
        if not report_file or not Path(report_file).exists():
            logger.error("[FAIL] No report file found. Run scraping first.")
            return results
        
        logger.info(f"[OK] Using existing report: {Path(report_file).name}")
        results['scraper'] = {'success': True, 'skipped': True, 'report_file': report_file}
    
    # ============================================================
    # STEP 2: LLM 분석 (OpenAI API로 분석 + AI 전략 생성)
    # ============================================================
    logger.info("\n[STEP 2/3] Starting LLM Analysis...")
    try:
        from analyzer.jd_analyzer import JDAnalyzer
        
        analyzer = JDAnalyzer()
        
        # Load scraped data
        with open(report_file, 'r', encoding='utf-8') as f:
            report_data = json.load(f)
        
        # Set context for AI strategy
        analyzer.analyzed_jobs = report_data.get('jobs', [])
        
        # Calculate skill frequency  
        for job in analyzer.analyzed_jobs:
            for skill in job.get('required_skills', []):
                analyzer.skill_frequency[skill] += 1
            for skill in job.get('preferred_skills', []):
                analyzer.skill_frequency[skill] += 1
        
        # Generate AI-powered insights
        top_skills = report_data.get('top_skills', [])
        trending_skills = report_data.get('trending_skills', [])
        
        logger.info("Generating AI-powered strategy recommendation...")
        ai_recommendation = analyzer._generate_recommendation(top_skills, trending_skills)
        
        # Update report with AI recommendation
        report_data['recommendation'] = ai_recommendation
        report_data['ai_generated'] = True
        report_data['analysis_timestamp'] = datetime.now().isoformat()
        
        # Save updated report
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        results['analyzer'] = {
            'success': True,
            'jobs_analyzed': len(analyzer.analyzed_jobs),
            'skills_found': len(analyzer.skill_frequency),
            'ai_recommendation': ai_recommendation[:100] + '...' if len(ai_recommendation) > 100 else ai_recommendation
        }
        logger.info(f"[OK] Analysis completed: {len(analyzer.analyzed_jobs)} jobs, AI strategy generated")
        
    except Exception as e:
        logger.error(f"[FAIL] Analysis error: {e}")
        import traceback
        traceback.print_exc()
        results['analyzer'] = {'success': False, 'error': str(e)}
        return results
    
    # ============================================================
    # STEP 3: 이메일 발송 (HTML 리포트)
    # ============================================================
    logger.info("\n[STEP 3/3] Sending Email Report...")
    try:
        from notifier.email_sender import EmailSender
        from jinja2 import Environment, FileSystemLoader
        
        email_sender = EmailSender()
        
        # Load final report data
        with open(report_file, 'r', encoding='utf-8') as f:
            final_report = json.load(f)
        
        # Prepare template data
        template_data = {
            'report_date': final_report.get('report_date', datetime.now().strftime('%Y-%m-%d')),
            'year': final_report.get('year', datetime.now().year),
            'total_jobs': final_report.get('total_jobs', 0),
            'skill_chart_data': final_report.get('skill_chart_data', []),
            'top_skills': final_report.get('top_skills', []),
            'trending_skills': final_report.get('trending_skills', []),
            'recommendation': final_report.get('recommendation', ''),
            'jobs': final_report.get('jobs', [])
        }
        
        # Render HTML report using Jinja2 template
        templates_dir = Path(__file__).resolve().parent / "templates"
        jinja_env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
        template = jinja_env.get_template("report.html")
        email_sender.report_html = template.render(**template_data)
        
        # Save report for debugging
        report_html_path = Path(__file__).resolve().parent / "data" / f"report_{datetime.now().strftime('%Y-%m-%d')}.html"
        with open(report_html_path, 'w', encoding='utf-8') as f:
            f.write(email_sender.report_html)
        logger.info(f"Report saved to: {report_html_path}")
        
        # Send email
        email_sent = email_sender.send_email()
        
        results['notifier'] = {
            'success': email_sent,
            'recipient': email_sender.recipient_email,
            'report_path': str(report_html_path)
        }
        
        if email_sent:
            logger.info(f"[OK] Email sent successfully to: {email_sender.recipient_email}")
        else:
            logger.error("[FAIL] Email sending returned False")
            
    except Exception as e:
        logger.error(f"[FAIL] Email error: {e}")
        import traceback
        traceback.print_exc()
        results['notifier'] = {'success': False, 'error': str(e)}
        return results
    
    # ============================================================
    # Complete
    # ============================================================
    scraper_ok = results['scraper'].get('success', False) if results['scraper'] else False
    analyzer_ok = results['analyzer'].get('success', False) if results['analyzer'] else False
    notifier_ok = results['notifier'].get('success', False) if results['notifier'] else False
    
    results['success'] = analyzer_ok and notifier_ok and (scraper_ok or skip_scrape)
    
    logger.info("\n" + "="*60)
    if results['success']:
        logger.info("[SUCCESS] Pipeline Completed!")
    else:
        logger.info("[PARTIAL] Pipeline completed with some failures")
    logger.info(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*60)
    
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='LinkedIn JD Analyzer Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--skip-scrape', 
        action='store_true',
        help='Skip scraping step (use existing data)'
    )
    parser.add_argument(
        '--report-file',
        type=str,
        help='Path to specific report file to use'
    )
    
    args = parser.parse_args()
    
    result = run_pipeline(
        skip_scrape=args.skip_scrape,
        report_file=args.report_file
    )
    
    print(f"\nFinal Result: {'SUCCESS' if result.get('success') else 'FAILED'}")
