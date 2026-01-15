import os
import re
import time
import json
import pickle
from pathlib import Path
from datetime import datetime
from collections import Counter
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Setup
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
load_dotenv(project_root / ".env")

EMAIL = os.getenv("LINKEDIN_EMAIL")
PASSWORD = os.getenv("LINKEDIN_PASSWORD")

# Cookie file path
COOKIE_FILE = project_root / "ai" / "linkedin_cookies.pkl"

# Tech skills to detect
TECH_SKILLS = [
    "Python", "SQL", "Spark", "AWS", "Azure", "GCP", "Snowflake", "Databricks",
    "Airflow", "Kafka", "Docker", "Kubernetes", "Terraform", "dbt", "ETL",
    "Java", "Scala", "Go", "Tableau", "Power BI", "Looker", "Redshift",
    "BigQuery", "PostgreSQL", "MongoDB", "Redis", "Hadoop", "Hive", "Presto",
    "Git", "CI/CD", "Linux", "REST API", "GraphQL", "Machine Learning", "ML",
    "Deep Learning", "TensorFlow", "PyTorch", "Pandas", "NumPy", "scikit-learn",
    "NLP", "Computer Vision", "Data Modeling", "Data Warehouse", "Data Lake"
]


def log(msg):
    """Print log message with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}")


import random
import undetected_chromedriver as uc

def get_random_delay(min_sec=1, max_sec=3):
    """Return a random delay to simulate human behavior."""
    return random.uniform(min_sec, max_sec)


def create_driver():
    """Create Chrome driver with undetected-chromedriver for advanced detection prevention."""
    log(" 브라우저 초기화 중 (undetected-chromedriver)...")
    
    options = uc.ChromeOptions()
    
    # 기본 옵션들
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=en-US")
    
    # undetected-chromedriver 사용 (자동으로 봇 탐지 우회)
    driver = uc.Chrome(options=options, use_subprocess=True)
    
    log(" 브라우저 초기화 완료 (undetected-chromedriver)")
    return driver


def save_cookies(driver):
    """Save cookies to file after successful login."""
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    cookies = driver.get_cookies()
    with open(COOKIE_FILE, 'wb') as f:
        pickle.dump(cookies, f)
    log(f" 쿠키 저장 완료: {COOKIE_FILE.name}")


def load_cookies(driver):
    """Load cookies from file.
    
    Returns:
        True if cookies loaded and session is valid, False otherwise.
    """
    if not COOKIE_FILE.exists():
        log(" 저장된 쿠키 없음 - 로그인 필요")
        return False
    
    try:
        # First go to LinkedIn domain (required before adding cookies)
        driver.get("https://www.linkedin.com")
        time.sleep(get_random_delay(1, 2))
        
        with open(COOKIE_FILE, 'rb') as f:
            cookies = pickle.load(f)
        
        for cookie in cookies:
            # Remove problematic attributes
            cookie.pop('sameSite', None)
            cookie.pop('expiry', None)
            try:
                driver.add_cookie(cookie)
            except Exception:
                pass
        
        log(" 쿠키 로드 완료 - 세션 확인 중...")
        
        # Verify session by checking if we can access feed
        driver.get("https://www.linkedin.com/feed/")
        time.sleep(get_random_delay(1.5, 3))
        
        # Check if we're logged in
        if "/feed" in driver.current_url or "/in/" in driver.current_url:
            log(" 쿠키 세션 유효 - 로그인 건너뛰기")
            return True
        else:
            log(" 쿠키 만료 - 다시 로그인 필요")
            return False
            
    except Exception as e:
        log(f" 쿠키 로드 실패: {e}")
        return False


def login(driver, use_cookies=True):
    """Login to LinkedIn with cookie support.
    
    Args:
        driver: Selenium WebDriver
        use_cookies: If True, try to use saved cookies first
    """
    # Try to use saved cookies first
    if use_cookies and load_cookies(driver):
        return  # Already logged in via cookies
    
    log(" 로그인 페이지 접속 중...")
    driver.get("https://www.linkedin.com/login")
    
    log(" 이메일/비밀번호 입력 중...")
    email_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "username")))
    
    # 인간처럼 천천히 타이핑
    for char in EMAIL:
        email_field.send_keys(char)
        time.sleep(random.uniform(0.05, 0.15))
    
    time.sleep(get_random_delay(0.3, 0.7))
    
    password_field = driver.find_element(By.ID, "password")
    for char in PASSWORD:
        password_field.send_keys(char)
        time.sleep(random.uniform(0.05, 0.15))
    
    time.sleep(get_random_delay(0.5, 1))
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    
    log(" 로그인 완료 대기 중... (보안 확인이 필요하면 직접 해결해주세요)")
    
    # Wait longer for potential CAPTCHA solving
    WebDriverWait(driver, 120).until(EC.url_contains("/feed"))
    log(" 로그인 성공")
    
    # Save cookies for future use
    save_cookies(driver)


def get_job_description(driver):
    """Extract job description from right panel."""
    selectors = [
        ".jobs-description__content",
        ".jobs-box__html-content",
        "[data-testid='expandable-text-box']",
        ".jobs-description",
        "#job-details"
    ]
    
    for sel in selectors:
        try:
            elem = driver.find_element(By.CSS_SELECTOR, sel)
            text = elem.text.strip()
            if text and len(text) > 50:
                return text
        except:
            continue
    return ""


def extract_skills(text):
    """Extract tech skills from description."""
    found_skills = []
    text_lower = text.lower()
    
    for skill in TECH_SKILLS:
        pattern = r'\b' + re.escape(skill.lower()) + r'\b'
        if re.search(pattern, text_lower):
            found_skills.append(skill)
    
    return found_skills


def extract_experience_years(text):
    """Extract years of experience from description."""
    patterns = [
        r'(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s*)?(?:experience|exp)',
        r'(\d+)\s*-\s*\d+\s*(?:years?|yrs?)',
        r'minimum\s*(?:of\s*)?(\d+)\s*(?:years?|yrs?)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            return int(match.group(1))
    return None


def extract_education(text):
    """Extract education requirements from description."""
    text_lower = text.lower()
    
    if "phd" in text_lower or "doctorate" in text_lower:
        return "PhD"
    elif "master" in text_lower or "m.s." in text_lower or "msc" in text_lower:
        return "Master's"
    elif "bachelor" in text_lower or "b.s." in text_lower or "bsc" in text_lower:
        return "Bachelor's"
    return None


def detect_visa_sponsorship(text):
    """Detect visa sponsorship status from description."""
    text_lower = text.lower()
    
    no_patterns = [
        "no visa sponsorship", "unable to sponsor", "not sponsor",
        "cannot sponsor", "must be authorized", "must have work authorization", "no sponsorship"
    ]
    
    yes_patterns = [
        "visa sponsorship available", "will sponsor", "sponsorship available", "visa assistance"
    ]
    
    for pattern in no_patterns:
        if pattern in text_lower:
            return False
    
    for pattern in yes_patterns:
        if pattern in text_lower:
            return True
    
    return None


def parse_job_details(description):
    """Parse job description to extract structured data."""
    skills = extract_skills(description)
    required_skills = skills[:min(5, len(skills))]
    preferred_skills = skills[5:min(10, len(skills))] if len(skills) > 5 else []
    
    return {
        "experience_years": extract_experience_years(description),
        "education": extract_education(description),
        "visa_sponsorship": detect_visa_sponsorship(description),
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
        "summary": description[:300] + "..." if len(description) > 300 else description
    }


def dismiss_popups(driver):
    """Dismiss any popups or modals that may block interaction."""
    popup_selectors = [
        # 일반적인 닫기 버튼들
        "button[data-tracking-control-name='public_jobs_contextual-sign-in-modal_modal_dismiss']",
        "button.artdeco-modal__dismiss",
        "button[aria-label='Dismiss']",
        "button[aria-label='닫기']",
        "button.msg-overlay-bubble-header__control--new-convo-btn",
        ".artdeco-toast-item__dismiss",
        # 메시징 오버레이 닫기
        "button.msg-overlay-bubble-header__control",
        # 구직/이직 준비하기 팝업 닫기
        "button.artdeco-button--circle",
        "svg[data-test-icon='close-medium']",
        # X 버튼 (SVG 포함)
        "button.artdeco-modal__dismiss svg",
    ]
    
    dismissed_count = 0
    for selector in popup_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for elem in elements:
                if elem.is_displayed():
                    driver.execute_script("arguments[0].click();", elem)
                    dismissed_count += 1
                    time.sleep(0.3)
        except:
            continue
    
    # ESC 키로 모달 닫기 시도
    try:
        from selenium.webdriver.common.keys import Keys
        body = driver.find_element(By.TAG_NAME, "body")
        body.send_keys(Keys.ESCAPE)
        time.sleep(0.5)
    except:
        pass
    
    if dismissed_count > 0:
        log(f" 팝업 {dismissed_count}개 닫음")
    
    return dismissed_count


def scrape_jobs(driver, search_url, max_jobs=25):
    """Scrape job listings by clicking each one."""
    log(f" 검색 페이지 접속 중...")
    log(f"   URL: {search_url}")
    driver.get(search_url)
    
    delay = get_random_delay(2, 4)
    log(f" 페이지 로딩 대기 ({delay:.1f}초)...")
    time.sleep(delay)
    
    # 팝업/모달 닫기
    dismiss_popups(driver)
    time.sleep(0.5)
    
    # Debug: Print current URL
    log(f" 현재 URL: {driver.current_url}")
    
    # Try multiple selectors for job list
    job_list_selectors = [
        ".jobs-search-results-list",
        ".scaffold-layout__list",
        ".jobs-search-results__list",
        "[data-results-list-container]"
    ]
    
    job_list_found = False
    for selector in job_list_selectors:
        try:
            log(f" 잡 리스트 찾는 중... (selector: {selector})")
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            log(f" 잡 리스트 발견: {selector}")
            job_list_found = True
            break
        except:
            log(f"    {selector} 없음")
            continue
    
    if not job_list_found:
        log("잡 리스트를 찾을 수 없음")
        log("페이지 소스 일부:")
        # Print a snippet of the page source for debugging
        page_source = driver.page_source
        if "sign-in" in page_source.lower() or "login" in page_source.lower():
            log("로그인이 필요한 페이지로 리다이렉트된 것 같습니다")
        if "no results" in page_source.lower():
            log("검색 결과가 없는 것 같습니다")
        
        # Try to find any job-related elements
        all_elements = driver.find_elements(By.CSS_SELECTOR, "[class*='job']")
        log(f"   'job' 관련 요소 개수: {len(all_elements)}")
        
        # Save screenshot for debugging
        screenshot_path = project_root / "data" / "debug_screenshot.png"
        screenshot_path.parent.mkdir(exist_ok=True)
        driver.save_screenshot(str(screenshot_path))
        log(f"   📸 스크린샷 저장: {screenshot_path}")
        
        return []
    
    # Try multiple selectors for job cards
    job_card_selectors = [
        ".jobs-search-results-list__list-item",
        ".scaffold-layout__list-item",
        ".jobs-search-results__list-item",
        "li[data-occludable-job-id]"
    ]
    
    jobs = []
    processed = set()
    
    for _ in range(max_jobs):
        cards = []
        for selector in job_card_selectors:
            cards = driver.find_elements(By.CSS_SELECTOR, selector)
            if cards:
                log(f"잡 카드 {len(cards)}개 발견 (selector: {selector})")
                break
        
        if not cards:
            log("잡 카드를 찾을 수 없음")
            break
        
        found_new = False
        for card in cards:
            try:
                link = card.find_element(By.CSS_SELECTOR, "a[href*='/jobs/view/']")
                job_id = link.get_attribute("href").split("/jobs/view/")[1].split("/")[0].split("?")[0]
                
                if job_id in processed:
                    continue
                
                processed.add(job_id)
                found_new = True
                
                log(f"공고 클릭 중... (ID: {job_id})")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
                time.sleep(get_random_delay(0.3, 0.8))
                driver.execute_script("arguments[0].click();", link)
                time.sleep(get_random_delay(1.5, 3))
                
                title = link.text.strip().split("\n")[0]
                
                try:
                    company = card.find_element(By.CSS_SELECTOR, ".artdeco-entity-lockup__subtitle").text.strip()
                except:
                    company = ""
                
                try:
                    location = card.find_element(By.CSS_SELECTOR, ".artdeco-entity-lockup__caption").text.strip()
                except:
                    location = ""
                
                log(f"상세 정보 추출 중... ({title})")
                description = get_job_description(driver)
                
                if description:
                    log(f"Description 길이: {len(description)}자")
                else:
                    log(f"Description 추출 실패")
                
                parsed = parse_job_details(description)
                
                job_data = {
                    "id": job_id,
                    "title": title,
                    "company": company,
                    "location": location,
                    "url": f"https://www.linkedin.com/jobs/view/{job_id}/",
                    "description": description,
                    **parsed
                }
                
                jobs.append(job_data)
                log(f"✓ [{len(jobs)}/{max_jobs}] {title} @ {company} | 스킬: {len(parsed['required_skills'])+len(parsed['preferred_skills'])}개")
                
                if len(jobs) >= max_jobs:
                    break
                    
            except Exception as e:
                log(f"에러: {str(e)[:50]}")
                continue
        
        if not found_new or len(jobs) >= max_jobs:
            break
            
        log("스크롤 다운...")
        try:
            scroll_container = driver.find_element(By.CSS_SELECTOR, ".jobs-search-results-list")
            scroll_amount = random.randint(300, 600)
            driver.execute_script(f"arguments[0].scrollTop += {scroll_amount};", scroll_container)
        except:
            scroll_amount = random.randint(300, 600)
            driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
        time.sleep(get_random_delay(0.8, 1.5))
    
    return jobs


def generate_report_data(jobs):
    """Generate data for report template."""
    all_skills = []
    for job in jobs:
        all_skills.extend(job.get("required_skills", []))
        all_skills.extend(job.get("preferred_skills", []))
    
    skill_counts = Counter(all_skills)
    max_count = max(skill_counts.values()) if skill_counts else 1
    
    skill_chart_data = [
        {"name": skill, "count": count, "percentage": round((count / max_count) * 100)}
        for skill, count in skill_counts.most_common(15)
    ]
    
    top_skills = [item["name"] for item in skill_chart_data[:5]]
    trending_skills = [item["name"] for item in skill_chart_data[5:10]]
    
    now = datetime.now()
    
    return {
        "report_date": now.strftime("%B %d, %Y"),
        "year": now.year,
        "total_jobs": len(jobs),
        "skill_chart_data": skill_chart_data,
        "top_skills": top_skills,
        "trending_skills": trending_skills,
        "recommendation": generate_recommendation(top_skills, trending_skills),
        "jobs": jobs
    }


def generate_recommendation(top_skills, trending_skills):
    """Generate recommendation text based on skills analysis."""
    if not top_skills:
        return "No specific recommendations available. Check back with more job data."
    
    rec = f"Based on today's analysis, focus on mastering {', '.join(top_skills[:3])} as they appear most frequently in job postings."
    
    if trending_skills:
        rec += f" Additionally, consider learning {trending_skills[0]} to stand out from other candidates."
    
    return rec


def save_data(jobs, report_data, filename_prefix="linkedin"):
    """Save jobs and report data to JSON files."""
    output_dir = project_root / "data"
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    jobs_path = output_dir / f"{filename_prefix}_jobs_{timestamp}.json"
    with open(jobs_path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
    
    report_path = output_dir / f"{filename_prefix}_report_{timestamp}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    
    log(f"{len(jobs)}개 잡 저장: {jobs_path}")
    log(f"리포트 데이터 저장: {report_path}")
    
    return jobs_path, report_path


def run_scraper(keywords="Data Engineer", location="Canada", max_jobs=25):
    """
    Run the scraper programmatically (for pipeline automation).
    Returns a result dictionary instead of using input() for waiting.
    """
    search_url = f"https://www.linkedin.com/jobs/search/?keywords={keywords.replace(' ', '%20')}&location={location}&f_TPR=r86400&sortBy=DD"
    
    log("=" * 50)
    log("LinkedIn Job Scraper (Automated Mode)")
    log(f"Keywords: {keywords}")
    log(f"Location: {location}")
    log("=" * 50)
    
    driver = create_driver()
    driver.maximize_window()
    
    result = {
        'success': False,
        'jobs_count': 0,
        'jobs_file': None,
        'report_file': None,
        'error': None
    }
    
    try:
        login(driver)
        
        log("")
        log("=" * 50)
        log("Starting job scraping...")
        log("=" * 50)
        
        jobs = scrape_jobs(driver, search_url, max_jobs=max_jobs)
        
        if jobs:
            log("")
            log("=" * 50)
            log("Generating report...")
            report_data = generate_report_data(jobs)
            jobs_path, report_path = save_data(jobs, report_data)
            
            result['success'] = True
            result['jobs_count'] = len(jobs)
            result['jobs_file'] = str(jobs_path)
            result['report_file'] = str(report_path)
            
            log("")
            log("=== Summary ===")
            log(f"Total jobs: {report_data['total_jobs']}")
            log(f"Top skills: {', '.join(report_data['top_skills'])}")
            log(f"Trending skills: {', '.join(report_data['trending_skills'])}")
        else:
            result['error'] = "No jobs found"
            log("")
            log("No jobs collected")
            
    except Exception as e:
        result['error'] = str(e)
        log(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        log("")
        log("Closing browser...")
        driver.quit()
    
    return result

def main(auto_mode=False):
    """Main function for standalone execution.
    
    Args:
        auto_mode: If True, skip input() wait at the end (for pipeline automation)
    """
    # 여러 키워드로 검색
    keywords_list = ["Data Engineer", "AI Engineer", "Data Scientist"]
    location = "Canada"
    max_jobs_per_keyword = 15  # 각 키워드당 최대 15개씩 (총 45개 목표)
    
    log("=" * 50)
    log("LinkedIn Job Scraper 시작")
    log(f"검색어: {', '.join(keywords_list)}")
    log(f"지역: {location}")
    log(f"키워드당 최대: {max_jobs_per_keyword}개")
    if auto_mode:
        log("Mode: Auto (파이프라인 실행)")
    log("=" * 50)
    
    driver = create_driver()
    driver.maximize_window()
    
    exit_code = 0
    all_jobs = []
    processed_ids = set()  # 중복 방지
    
    try:
        login(driver)
        
        for keyword in keywords_list:
            log("")
            log("=" * 50)
            log(f"채용공고 스크래핑: '{keyword}'")
            log("=" * 50)
            
            search_url = f"https://www.linkedin.com/jobs/search/?keywords={keyword.replace(' ', '%20')}&location={location}&f_TPR=r86400&sortBy=DD"
            
            jobs = scrape_jobs(driver, search_url, max_jobs=max_jobs_per_keyword)
            
            # 중복 제거하면서 추가
            new_jobs = 0
            for job in jobs:
                if job['id'] not in processed_ids:
                    processed_ids.add(job['id'])
                    job['search_keyword'] = keyword  # 어떤 키워드로 검색되었는지 표시
                    all_jobs.append(job)
                    new_jobs += 1
            
            log(f"✓ '{keyword}': {new_jobs}개 새 공고 추가 (중복 제외)")
            
            # 키워드 간 딜레이 (봇 탐지 방지)
            if keyword != keywords_list[-1]:
                delay = get_random_delay(3, 5)
                log(f" 다음 검색까지 {delay:.1f}초 대기...")
                time.sleep(delay)
        
        if all_jobs:
            log("")
            log("=" * 50)
            log("리포트 생성 중...")
            report_data = generate_report_data(all_jobs)
            save_data(all_jobs, report_data)
            
            log("")
            log("=== 결과 요약 ===")
            log(f"총 수집 공고: {report_data['total_jobs']}개")
            log(f"Top 스킬: {', '.join(report_data['top_skills'])}")
            log(f"Trending 스킬: {', '.join(report_data['trending_skills'])}")
        else:
            log("")
            log("수집된 공고가 없습니다")
            log("- 검색 결과가 없거나")
            log("- 페이지 구조가 변경되었을 수 있습니다")
            log("- data/debug_screenshot.png 를 확인해주세요")
            exit_code = 1
            
    except Exception as e:
        log(f"에러 발생: {e}")
        import traceback
        traceback.print_exc()
        exit_code = 1
    finally:
        log("")
        log("브라우저 종료 중...")
        if not auto_mode:
            input("Enter 키를 누르면 브라우저가 닫힙니다...")
        driver.quit()
    
    return exit_code


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='LinkedIn Job Scraper')
    parser.add_argument('--auto', action='store_true', 
                        help='Auto mode: skip input() wait at the end (for pipeline)')
    
    args = parser.parse_args()
    
    exit_code = main(auto_mode=args.auto)
    exit(exit_code)
