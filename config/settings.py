"""
LinkedIn JD Analyzer - Configuration Settings
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

# LinkedIn Settings
LINKEDIN_CONFIG = {
    "email": os.getenv("LINKEDIN_EMAIL", ""),
    "password": os.getenv("LINKEDIN_PASSWORD", ""),
    "search_keywords": [
        "Data Engineer",
        "Data Scientist",
        "ML Engineer",
        "Machine Learning Engineer"
    ],
    "location": "Canada",
    "time_filter": "r86400",  # Last 24 hours
    "max_jobs_per_search": 25,
}

# OpenAI Settings
OPENAI_CONFIG = {
    "api_key": os.getenv("OPENAI_API_KEY", ""),
    "model": "gpt-4o-mini",  # Cost-effective for analysis
    "max_tokens": 2000,
}

# Email Settings
EMAIL_CONFIG = {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": os.getenv("SENDER_EMAIL", ""),
    "sender_password": os.getenv("SENDER_PASSWORD", ""),  # Gmail App Password
    "recipient_email": os.getenv("RECIPIENT_EMAIL", ""),
}

# Scheduler Settings
SCHEDULER_CONFIG = {
    "hour": 7,  # 7 AM
    "minute": 0,
    "timezone": "America/Toronto",  # Canada Eastern Time
}

# Scraper Settings
SCRAPER_CONFIG = {
    "headless": False,  # 브라우저 보이기
    "page_load_timeout": 30,
    "implicit_wait": 10,
    "rate_limit_delay": (2, 5),  # Random delay between 2-5 seconds
}

# Data Storage
STORAGE_CONFIG = {
    "jobs_file": DATA_DIR / "jobs.json",
    "history_file": DATA_DIR / "history.json",
    "analysis_file": DATA_DIR / "analysis.json",
    "context_file": DATA_DIR / "context.json",
}

# Orchestrator Settings
ORCHESTRATOR_CONFIG = {
    "max_retries": 3,
    "stop_on_error": True,
    "auto_save_context": True,
}
