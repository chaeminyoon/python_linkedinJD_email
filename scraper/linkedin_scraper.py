"""
LinkedIn JD Scraper Module

LinkedIn에서 캐나다 Data Engineer/Scientist 채용공고를 자동으로 수집합니다.
"""

import json
import random
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)
from webdriver_manager.chrome import ChromeDriverManager

# Import settings
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config.settings import (
    LINKEDIN_CONFIG,
    SCRAPER_CONFIG,
    STORAGE_CONFIG,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LinkedInScraper:
    """LinkedIn 채용공고 스크래퍼 클래스"""

    # LinkedIn URL constants
    LOGIN_URL = "https://www.linkedin.com/login"
    JOBS_BASE_URL = "https://www.linkedin.com/jobs/search/"

    def __init__(self, headless: bool = None):
        """
        LinkedInScraper 초기화

        Args:
            headless: 헤드리스 모드 여부 (None이면 설정 파일 사용)
        """
        self.headless = headless if headless is not None else SCRAPER_CONFIG["headless"]
        self.driver: Optional[webdriver.Chrome] = None
        self.collected_jobs: List[Dict[str, Any]] = []
        self.seen_job_ids: set = set()

        # Load existing job IDs for deduplication
        self._load_existing_job_ids()

    def _load_existing_job_ids(self) -> None:
        """기존에 수집한 job_id들을 로드하여 중복 방지"""
        jobs_file = STORAGE_CONFIG["jobs_file"]
        if jobs_file.exists():
            try:
                with open(jobs_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for job in data.get("jobs", []):
                        self.seen_job_ids.add(job.get("job_id"))
                logger.info(f"Loaded {len(self.seen_job_ids)} existing job IDs for deduplication")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load existing jobs: {e}")

    def _init_driver(self) -> None:
        """Chrome WebDriver 초기화"""
        logger.info("Initializing Chrome WebDriver...")

        chrome_options = Options()

        if self.headless:
            chrome_options.add_argument("--headless=new")

        # Anti-detection settings
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # Disable automation flags
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)

        # Set timeouts
        self.driver.set_page_load_timeout(SCRAPER_CONFIG["page_load_timeout"])
        self.driver.implicitly_wait(SCRAPER_CONFIG["implicit_wait"])

        # Execute CDP commands to hide webdriver
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    })
                """
            }
        )

        logger.info("Chrome WebDriver initialized successfully")

    def _random_delay(self) -> None:
        """Rate limiting을 위한 랜덤 딜레이"""
        min_delay, max_delay = SCRAPER_CONFIG["rate_limit_delay"]
        delay = random.uniform(min_delay, max_delay)
        logger.debug(f"Waiting {delay:.2f} seconds...")
        time.sleep(delay)

    def login(self) -> bool:
        """
        LinkedIn 로그인

        Returns:
            bool: 로그인 성공 여부
        """
        email = LINKEDIN_CONFIG["email"]
        password = LINKEDIN_CONFIG["password"]

        if not email or not password:
            logger.error("LinkedIn credentials not configured. Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD environment variables.")
            return False

        try:
            logger.info("Navigating to LinkedIn login page...")
            self.driver.get(self.LOGIN_URL)
            self._random_delay()

            # Enter email
            email_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            email_field.clear()
            email_field.send_keys(email)

            # Enter password
            password_field = self.driver.find_element(By.ID, "password")
            password_field.clear()
            password_field.send_keys(password)

            # Click login button
            login_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            login_button.click()

            self._random_delay()

            # Verify login success
            WebDriverWait(self.driver, 15).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".global-nav")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".feed-identity-module")),
                    EC.url_contains("/feed")
                )
            )

            logger.info("Successfully logged in to LinkedIn")
            return True

        except TimeoutException:
            logger.error("Login timeout - may need to handle security verification")
            return False
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    def search_jobs(self, keyword: str = None) -> List[Dict[str, Any]]:
        """
        채용공고 검색

        Args:
            keyword: 검색 키워드 (None이면 설정 파일의 모든 키워드 사용)

        Returns:
            List[Dict]: 검색된 채용공고 리스트
        """
        keywords = [keyword] if keyword else LINKEDIN_CONFIG["search_keywords"]
        location = LINKEDIN_CONFIG["location"]
        time_filter = LINKEDIN_CONFIG["time_filter"]
        max_jobs = LINKEDIN_CONFIG["max_jobs_per_search"]

        all_jobs = []

        for search_keyword in keywords:
            logger.info(f"Searching jobs for keyword: {search_keyword}")

            # Build search URL with filters
            search_url = (
                f"{self.JOBS_BASE_URL}?"
                f"keywords={search_keyword.replace(' ', '%20')}"
                f"&location={location.replace(' ', '%20')}"
                f"&f_TPR={time_filter}"  # Time posted filter (24h)
                f"&sortBy=DD"  # Sort by date
            )

            try:
                self.driver.get(search_url)
                self._random_delay()

                # Wait for job listings to load
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".jobs-search-results-list"))
                )

                # Scroll to load more jobs
                jobs_found = self._scroll_and_collect_jobs(max_jobs)

                logger.info(f"Found {len(jobs_found)} jobs for keyword: {search_keyword}")
                all_jobs.extend(jobs_found)

            except TimeoutException:
                logger.warning(f"Timeout while searching for {search_keyword}")
            except Exception as e:
                logger.error(f"Error searching for {search_keyword}: {e}")

            self._random_delay()

        # Deduplicate jobs
        unique_jobs = self._deduplicate_jobs(all_jobs)
        logger.info(f"Total unique jobs found: {len(unique_jobs)}")

        return unique_jobs

    def _scroll_and_collect_jobs(self, max_jobs: int) -> List[Dict[str, Any]]:
        """
        스크롤하면서 채용공고 카드 수집

        Args:
            max_jobs: 최대 수집 개수

        Returns:
            List[Dict]: 수집된 채용공고 기본 정보
        """
        collected = []
        scroll_count = 0
        max_scrolls = 10

        while len(collected) < max_jobs and scroll_count < max_scrolls:
            # Find job cards
            job_cards = self.driver.find_elements(
                By.CSS_SELECTOR,
                ".jobs-search-results__list-item"
            )

            for card in job_cards:
                if len(collected) >= max_jobs:
                    break

                try:
                    job_info = self._extract_job_card_info(card)
                    if job_info and job_info["job_id"] not in self.seen_job_ids:
                        collected.append(job_info)
                        self.seen_job_ids.add(job_info["job_id"])
                except Exception as e:
                    logger.debug(f"Failed to extract job card: {e}")
                    continue

            # Scroll down
            self.driver.execute_script(
                "arguments[0].scrollTop = arguments[0].scrollHeight",
                self.driver.find_element(By.CSS_SELECTOR, ".jobs-search-results-list")
            )
            self._random_delay()
            scroll_count += 1

        return collected

    def _extract_job_card_info(self, card) -> Optional[Dict[str, Any]]:
        """
        채용공고 카드에서 기본 정보 추출

        Args:
            card: Selenium WebElement (job card)

        Returns:
            Dict: 채용공고 기본 정보 또는 None
        """
        try:
            # Get job ID from data attribute
            job_id = card.get_attribute("data-occludable-job-id")
            if not job_id:
                # Try alternative method
                link_elem = card.find_element(By.CSS_SELECTOR, "a.job-card-list__title")
                href = link_elem.get_attribute("href")
                job_id = href.split("/view/")[1].split("/")[0] if "/view/" in href else None

            if not job_id:
                return None

            # Extract basic info
            title_elem = card.find_element(By.CSS_SELECTOR, ".job-card-list__title")
            company_elem = card.find_element(By.CSS_SELECTOR, ".job-card-container__primary-description")
            location_elem = card.find_element(By.CSS_SELECTOR, ".job-card-container__metadata-item")

            # Get link
            link = title_elem.get_attribute("href")
            if link and "?" in link:
                link = link.split("?")[0]

            return {
                "job_id": job_id,
                "title": title_elem.text.strip(),
                "company": company_elem.text.strip(),
                "location": location_elem.text.strip(),
                "url": link,
            }

        except NoSuchElementException:
            return None
        except Exception as e:
            logger.debug(f"Error extracting job card info: {e}")
            return None

    def extract_job_details(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """
        개별 채용공고의 상세 정보 추출

        Args:
            job: 기본 채용공고 정보

        Returns:
            Dict: 상세 정보가 포함된 채용공고
        """
        job_id = job.get("job_id")
        job_url = job.get("url")

        if not job_url:
            job_url = f"https://www.linkedin.com/jobs/view/{job_id}"

        try:
            logger.info(f"Extracting details for job: {job.get('title', job_id)}")
            self.driver.get(job_url)
            self._random_delay()

            # Wait for job description to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".jobs-description"))
            )

            # Click "See more" button if present
            try:
                see_more_btn = self.driver.find_element(
                    By.CSS_SELECTOR,
                    ".jobs-description__footer-button"
                )
                see_more_btn.click()
                time.sleep(0.5)
            except NoSuchElementException:
                pass

            # Extract description
            description_elem = self.driver.find_element(
                By.CSS_SELECTOR,
                ".jobs-description__content"
            )
            description = description_elem.text.strip()

            # Try to extract posted date
            posted_date = self._extract_posted_date()

            # Try to extract requirements
            requirements = self._extract_requirements(description)

            # Update job with details
            job.update({
                "description": description,
                "posted_date": posted_date,
                "requirements": requirements,
                "scraped_at": datetime.now().isoformat(),
            })

            return job

        except TimeoutException:
            logger.warning(f"Timeout loading job details for {job_id}")
            job["description"] = ""
            job["posted_date"] = None
            job["requirements"] = []
            return job
        except Exception as e:
            logger.error(f"Error extracting job details for {job_id}: {e}")
            job["description"] = ""
            job["posted_date"] = None
            job["requirements"] = []
            return job

    def _extract_posted_date(self) -> Optional[str]:
        """게시 날짜 추출"""
        try:
            # Try different selectors for posted date
            selectors = [
                ".jobs-unified-top-card__posted-date",
                ".jobs-unified-top-card__subtitle-secondary-grouping span",
                ".job-details-jobs-unified-top-card__primary-description-container span"
            ]

            for selector in selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    date_text = elem.text.strip()
                    if date_text:
                        # Parse relative date to absolute date
                        return self._parse_relative_date(date_text)
                except NoSuchElementException:
                    continue

            return datetime.now().strftime("%Y-%m-%d")

        except Exception:
            return datetime.now().strftime("%Y-%m-%d")

    def _parse_relative_date(self, date_text: str) -> str:
        """상대 날짜 텍스트를 절대 날짜로 변환"""
        from datetime import timedelta

        today = datetime.now()
        date_text_lower = date_text.lower()

        if "just now" in date_text_lower or "moment" in date_text_lower:
            return today.strftime("%Y-%m-%d")
        elif "hour" in date_text_lower:
            return today.strftime("%Y-%m-%d")
        elif "day" in date_text_lower:
            try:
                days = int(''.join(filter(str.isdigit, date_text_lower)) or 1)
                return (today - timedelta(days=days)).strftime("%Y-%m-%d")
            except:
                return today.strftime("%Y-%m-%d")
        elif "week" in date_text_lower:
            try:
                weeks = int(''.join(filter(str.isdigit, date_text_lower)) or 1)
                return (today - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
            except:
                return today.strftime("%Y-%m-%d")
        else:
            return today.strftime("%Y-%m-%d")

    def _extract_requirements(self, description: str) -> List[str]:
        """
        JD에서 요구사항 추출 (키워드 기반)

        Args:
            description: 채용공고 설명

        Returns:
            List[str]: 추출된 요구사항/기술 스택
        """
        # Common tech keywords to look for
        tech_keywords = [
            # Programming Languages
            "Python", "Java", "Scala", "R", "SQL", "JavaScript", "Go", "Rust",
            # Big Data
            "Spark", "Hadoop", "Kafka", "Flink", "Hive", "Presto", "Trino",
            # Cloud
            "AWS", "GCP", "Azure", "S3", "EC2", "Lambda", "Redshift", "BigQuery",
            "Snowflake", "Databricks",
            # Data Tools
            "Airflow", "dbt", "Luigi", "Prefect", "Dagster",
            # Databases
            "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch",
            "Cassandra", "DynamoDB",
            # ML/AI
            "TensorFlow", "PyTorch", "Scikit-learn", "Keras", "MLflow",
            "SageMaker", "Kubeflow",
            # DevOps
            "Docker", "Kubernetes", "Terraform", "CI/CD", "Git", "Jenkins",
            # Data Visualization
            "Tableau", "Power BI", "Looker", "Metabase",
        ]

        found_requirements = []
        description_lower = description.lower()

        for keyword in tech_keywords:
            if keyword.lower() in description_lower:
                found_requirements.append(keyword)

        return found_requirements

    def _deduplicate_jobs(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """중복 채용공고 제거"""
        seen_ids = set()
        unique_jobs = []

        for job in jobs:
            job_id = job.get("job_id")
            if job_id and job_id not in seen_ids:
                seen_ids.add(job_id)
                unique_jobs.append(job)

        return unique_jobs

    def save_jobs(self, jobs: List[Dict[str, Any]] = None) -> str:
        """
        수집된 채용공고를 JSON 파일로 저장

        Args:
            jobs: 저장할 채용공고 리스트 (None이면 self.collected_jobs 사용)

        Returns:
            str: 저장된 파일 경로
        """
        jobs_to_save = jobs if jobs is not None else self.collected_jobs

        output_data = {
            "jobs": jobs_to_save,
            "scraped_at": datetime.now().isoformat(),
            "total_count": len(jobs_to_save),
        }

        output_path = STORAGE_CONFIG["jobs_file"]

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved {len(jobs_to_save)} jobs to {output_path}")
        return str(output_path)

    def run(self, input_data: Any = None) -> Dict[str, Any]:
        """
        전체 스크래핑 프로세스 실행

        Args:
            input_data: Input data from orchestrator (not used, for compatibility)

        Returns:
            Dict: 실행 결과 정보
        """
        start_time = datetime.now()
        result = {
            "status": "failed",
            "jobs_found": 0,
            "output_file": None,
            "duration_seconds": 0,
            "errors": [],
        }

        try:
            # Initialize WebDriver
            self._init_driver()

            # Login to LinkedIn
            if not self.login():
                result["errors"].append("Failed to login to LinkedIn")
                return result

            # Search for jobs
            basic_jobs = self.search_jobs()

            if not basic_jobs:
                logger.warning("No jobs found")
                result["status"] = "completed"
                result["jobs_found"] = 0
                self.save_jobs([])
                return result

            # Extract details for each job
            detailed_jobs = []
            for job in basic_jobs:
                detailed_job = self.extract_job_details(job)
                detailed_jobs.append(detailed_job)
                self._random_delay()

            self.collected_jobs = detailed_jobs

            # Save to file
            output_file = self.save_jobs(detailed_jobs)

            # Update result
            result["status"] = "completed"
            result["jobs_found"] = len(detailed_jobs)
            result["output_file"] = output_file

            logger.info(f"Scraping completed. Found {len(detailed_jobs)} jobs.")

        except WebDriverException as e:
            logger.error(f"WebDriver error: {e}")
            result["errors"].append(f"WebDriver error: {str(e)}")
        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            result["errors"].append(f"Scraping error: {str(e)}")
        finally:
            # Clean up
            if self.driver:
                self.driver.quit()
                logger.info("WebDriver closed")

            end_time = datetime.now()
            result["duration_seconds"] = (end_time - start_time).total_seconds()

        return result

    def __enter__(self):
        """Context manager entry"""
        self._init_driver()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self.driver:
            self.driver.quit()


# CLI Entry Point
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LinkedIn Job Scraper")
    parser.add_argument(
        "--headless",
        action="store_true",
        default=None,
        help="Run in headless mode"
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run with browser visible"
    )
    parser.add_argument(
        "--keyword",
        type=str,
        help="Search for specific keyword only"
    )

    args = parser.parse_args()

    # Determine headless mode
    headless = None
    if args.headless:
        headless = True
    elif args.no_headless:
        headless = False

    # Run scraper
    scraper = LinkedInScraper(headless=headless)
    result = scraper.run()

    print(f"\n{'='*50}")
    print(f"Scraping Result:")
    print(f"  Status: {result['status']}")
    print(f"  Jobs Found: {result['jobs_found']}")
    print(f"  Duration: {result['duration_seconds']:.2f} seconds")
    if result['output_file']:
        print(f"  Output File: {result['output_file']}")
    if result['errors']:
        print(f"  Errors: {result['errors']}")
    print(f"{'='*50}")
        for selector in desc_selectors:
            try:
                elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                text = elem.text.strip()
                if text and len(text) > 50:
                    return text
            except:
                continue

        return ""

    def extract_job_details(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """
        개별 채용공고의 상세 정보 추출 (URL 직접 방문 방식 - fallback)

        Args:
            job: 기본 채용공고 정보

        Returns:
            Dict: 상세 정보가 포함된 채용공고
        """
        job_id = job.get("job_id")
        job_url = job.get("url")

        if not job_url:
            job_url = f"https://www.linkedin.com/jobs/view/{job_id}"

        try:
            logger.info(f"Extracting details for job: {job.get('title', job_id)}")
            self.driver.get(job_url)
            self._random_delay()

            # Wait for job description to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".jobs-description"))
            )

            # Click "See more" button if present
            try:
                see_more_btn = self.driver.find_element(
                    By.CSS_SELECTOR,
                    ".jobs-description__footer-button"
                )
                see_more_btn.click()
                time.sleep(0.5)
            except NoSuchElementException:
                pass

            # Extract description
            description_elem = self.driver.find_element(
                By.CSS_SELECTOR,
                ".jobs-description__content"
            )
            description = description_elem.text.strip()

            # Try to extract posted date
            posted_date = self._extract_posted_date()

            # Try to extract requirements
            requirements = self._extract_requirements(description)

            # Update job with details
            job.update({
                "description": description,
                "posted_date": posted_date,
                "requirements": requirements,
                "scraped_at": datetime.now().isoformat(),
            })

            return job

        except TimeoutException:
            logger.warning(f"Timeout loading job details for {job_id}")
            job["description"] = ""
            job["posted_date"] = None
            job["requirements"] = []
            return job
        except Exception as e:
            logger.error(f"Error extracting job details for {job_id}: {e}")
            job["description"] = ""
            job["posted_date"] = None
            job["requirements"] = []
            return job

    def _extract_posted_date(self) -> Optional[str]:
        """게시 날짜 추출"""
        try:
            # Try different selectors for posted date
            selectors = [
                ".jobs-unified-top-card__posted-date",
                ".jobs-unified-top-card__subtitle-secondary-grouping span",
                ".job-details-jobs-unified-top-card__primary-description-container span"
            ]

            for selector in selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    date_text = elem.text.strip()
                    if date_text:
                        # Parse relative date to absolute date
                        return self._parse_relative_date(date_text)
                except NoSuchElementException:
                    continue

            return datetime.now().strftime("%Y-%m-%d")

        except Exception:
            return datetime.now().strftime("%Y-%m-%d")

    def _parse_relative_date(self, date_text: str) -> str:
        """상대 날짜 텍스트를 절대 날짜로 변환"""
        from datetime import timedelta

        today = datetime.now()
        date_text_lower = date_text.lower()

        if "just now" in date_text_lower or "moment" in date_text_lower:
            return today.strftime("%Y-%m-%d")
        elif "hour" in date_text_lower:
            return today.strftime("%Y-%m-%d")
        elif "day" in date_text_lower:
            try:
                days = int(''.join(filter(str.isdigit, date_text_lower)) or 1)
                return (today - timedelta(days=days)).strftime("%Y-%m-%d")
            except:
                return today.strftime("%Y-%m-%d")
        elif "week" in date_text_lower:
            try:
                weeks = int(''.join(filter(str.isdigit, date_text_lower)) or 1)
                return (today - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
            except:
                return today.strftime("%Y-%m-%d")
        else:
            return today.strftime("%Y-%m-%d")

    def _extract_requirements(self, description: str) -> List[str]:
        """
        JD에서 요구사항 추출 (키워드 기반)

        Args:
            description: 채용공고 설명

        Returns:
            List[str]: 추출된 요구사항/기술 스택
        """
        # Common tech keywords to look for
        tech_keywords = [
            # Programming Languages
            "Python", "Java", "Scala", "R", "SQL", "JavaScript", "Go", "Rust",
            # Big Data
            "Spark", "Hadoop", "Kafka", "Flink", "Hive", "Presto", "Trino",
            # Cloud
            "AWS", "GCP", "Azure", "S3", "EC2", "Lambda", "Redshift", "BigQuery",
            "Snowflake", "Databricks",
            # Data Tools
            "Airflow", "dbt", "Luigi", "Prefect", "Dagster",
            # Databases
            "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch",
            "Cassandra", "DynamoDB",
            # ML/AI
            "TensorFlow", "PyTorch", "Scikit-learn", "Keras", "MLflow",
            "SageMaker", "Kubeflow",
            # DevOps
            "Docker", "Kubernetes", "Terraform", "CI/CD", "Git", "Jenkins",
            # Data Visualization
            "Tableau", "Power BI", "Looker", "Metabase",
        ]

        found_requirements = []
        description_lower = description.lower()

        for keyword in tech_keywords:
            if keyword.lower() in description_lower:
                found_requirements.append(keyword)

        return found_requirements

    def _deduplicate_jobs(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """중복 채용공고 제거"""
        seen_ids = set()
        unique_jobs = []

        for job in jobs:
            job_id = job.get("job_id")
            if job_id and job_id not in seen_ids:
                seen_ids.add(job_id)
                unique_jobs.append(job)

        return unique_jobs

    def save_jobs(self, jobs: List[Dict[str, Any]] = None) -> str:
        """
        수집된 채용공고를 JSON 파일로 저장

        Args:
            jobs: 저장할 채용공고 리스트 (None이면 self.collected_jobs 사용)

        Returns:
            str: 저장된 파일 경로
        """
        jobs_to_save = jobs if jobs is not None else self.collected_jobs

        output_data = {
            "jobs": jobs_to_save,
            "scraped_at": datetime.now().isoformat(),
            "total_count": len(jobs_to_save),
        }

        output_path = STORAGE_CONFIG["jobs_file"]

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved {len(jobs_to_save)} jobs to {output_path}")
        return str(output_path)

    def _extract_details_from_list(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        검색 결과 리스트의 각 항목을 클릭하여 우측 패널에서 상세 정보 추출

        Args:
            jobs: 기본 정보가 담긴 채용공고 리스트

        Returns:
            List[Dict]: 상세 정보가 업데이트된 리스트
        """
        updated_jobs = []
        
        logger.info(f"Starting detailed extraction for {len(jobs)} jobs...")

        for index, job in enumerate(jobs):
            job_id = job.get("job_id")
            title = job.get("title", "Unknown")
            
            logger.info(f"[{index+1}/{len(jobs)}] Extracting details for: {title} ({job_id})")

            try:
                # 1. Find the job card in the list
                # data-occludable-job-id is usually on the list item (li) or a div
                card_selector = f"[data-occludable-job-id='{job_id}']"
                
                try:
                    card_elem = self.driver.find_element(By.CSS_SELECTOR, card_selector)
                except NoSuchElementException:
                    # If not found, maybe it's scrolled out of view and removed from DOM?
                    # Try to scroll to it using Javascript if possible, or just fail this one.
                    # Since we just scrolled through them, they might still be there or we might need to re-find.
                    # For simplcity, let's try finding by ID if it's an li
                    logger.warning(f"  - Card element not found for {job_id}")
                    continue

                # 2. Click the card
                # Scroll into view first
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card_elem)
                time.sleep(0.5)
                
                # Click logic - try JS click if normal click fails
                try:
                    card_elem.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", card_elem)
                
                self._random_delay()

                # 3. Wait for the right pane to load
                # We can check if the title in the right pane matches the clicked job title or ID
                # This could be brittle, so a simple wait for description container might be safer for now
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".jobs-search__right-rail"))
                    )
                except TimeoutException:
                    pass # Just proceed to try finding description

                # 4. Extract Description from Right Pane
                # LinkedIn Right Pane Selectors (might vary)
                desc_selectors = [
                    ".jobs-description__content",
                    "#job-details",
                    ".jobs-search__job-details--container" 
                ]
                
                description = ""
                for selector in desc_selectors:
                    try:
                        desc_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                        description = desc_elem.text.strip()
                        if description:
                            break
                    except NoSuchElementException:
                        continue
                
                if not description:
                    logger.warning("  - Description not found")

                # 5. Extract Details (Posted Date, Requirements) same as before
                posted_date = self._extract_posted_date()
                requirements = self._extract_requirements(description)

                # 6. Update Job Object
                job_update = job.copy()
                job_update.update({
                    "description": description,
                    "posted_date": posted_date,
                    "requirements": requirements,
                    "scraped_at": datetime.now().isoformat(),
                })
                
                updated_jobs.append(job_update)

            except Exception as e:
                logger.error(f"  - Error extracting details for {job_id}: {e}")
                # Add basic job info even if failed, to avoid losing it? 
                # Or keep it as is. Let's keep existing info.
                updated_jobs.append(job)
                continue

        return updated_jobs

    def run(self, input_data: Any = None, skip_details: bool = False) -> Dict[str, Any]:
        """
        전체 스크래핑 프로세스 실행

        Args:
            input_data: Input data from orchestrator (not used, for compatibility)
            skip_details: True면 상세 정보 추출 건너뛰기 (빠른 테스트용)

        Returns:
            Dict: 실행 결과 정보
        """
        start_time = datetime.now()
        result = {
            "status": "failed",
            "jobs_found": 0,
            "output_file": None,
            "duration_seconds": 0,
            "errors": [],
        }

        try:
            # Initialize WebDriver
            self._init_driver()

            # Login to LinkedIn
            if not self.login():
                result["errors"].append("Failed to login to LinkedIn")
                return result

            # Search for jobs
            basic_jobs = self.search_jobs()

            if not basic_jobs:
                logger.warning("No jobs found")
                result["status"] = "completed"
                result["jobs_found"] = 0
                self.save_jobs([])
                return result

            # Save basic jobs immediately (in case of interruption)
            logger.info(f"Saving {len(basic_jobs)} basic jobs...")
            self.save_jobs(basic_jobs)

            if skip_details:
                # 빠른 테스트: 상세 정보 건너뛰기
                logger.info("Skipping detail extraction (quick mode)")
                self.collected_jobs = basic_jobs
                output_file = STORAGE_CONFIG["jobs_file"]
            else:
                # 검색 결과 페이지에서 클릭 방식으로 상세 정보 추출
                logger.info("Extracting details by clicking each job in the list...")
                detailed_jobs = self._extract_details_from_list(basic_jobs)
                self.collected_jobs = detailed_jobs
                output_file = self.save_jobs(detailed_jobs)

            # Update result
            result["status"] = "completed"
            result["jobs_found"] = len(self.collected_jobs)
            result["output_file"] = str(output_file)

            logger.info(f"Scraping completed. Found {len(self.collected_jobs)} jobs.")

        except WebDriverException as e:
            logger.error(f"WebDriver error: {e}")
            result["errors"].append(f"WebDriver error: {str(e)}")
        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            result["errors"].append(f"Scraping error: {str(e)}")
        finally:
            # Clean up
            if self.driver:
                self.driver.quit()
                logger.info("WebDriver closed")

            end_time = datetime.now()
            result["duration_seconds"] = (end_time - start_time).total_seconds()

        return result

    def __enter__(self):
        """Context manager entry"""
        self._init_driver()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self.driver:
            self.driver.quit()


# CLI Entry Point
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LinkedIn Job Scraper")
    parser.add_argument(
        "--headless",
        action="store_true",
        default=None,
        help="Run in headless mode"
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run with browser visible"
    )
    parser.add_argument(
        "--keyword",
        type=str,
        help="Search for specific keyword only"
    )
    parser.add_argument(
        "--skip-details",
        action="store_true",
        help="Skip detailed job extraction (quicker)"
    )

    args = parser.parse_args()

    # Determine headless mode
    headless = None
    if args.headless:
        headless = True
    elif args.no_headless:
        headless = False

    # Run scraper
    scraper = LinkedInScraper(headless=headless)
    result = scraper.run(skip_details=args.skip_details)

    print(f"\n{'='*50}")
    print(f"Scraping Result:")
    print(f"  Status: {result['status']}")
    if result['output_file']:
        print(f"  Output File: {result['output_file']}")
    if result['errors']:
        print(f"  Errors: {result['errors']}")
    print(f"{'='*50}")
