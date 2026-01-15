# LinkedIn JD Analyzer

Automated system for scraping, analyzing, and reporting on Data Engineer/Scientist job postings from LinkedIn. It uses AI to extract key skills and insights, delivering a daily email report to help job seekers stay competitive.

## Features

- **Automated Scraping**: Stealthily scrapes job postings from LinkedIn using `undetected-chromedriver` to bypass bot detection.
- **Multi-Keyword Search**: Supports searching for multiple job titles in a single run (e.g., Data Engineer, AI Engineer, Data Scientist).
- **AI-Powered Analysis**: Uses OpenAI GPT models to extract:
    - Required and preferred technical skills
    - Years of experience required
    - Visa sponsorship availability
    - Strategic career advice
- **Daily Email Reports**: Sends a beautifully formatted HTML email report with:
    - Market trends and skill frequency charts
    - Detailed job listings with tags
    - Personalized AI career strategy and actionable advice
- **Bot Detection Bypass**: Implements advanced stealth techniques including random delays, human-like interaction simulation, and browser fingerprint spoofing.

## Project Structure

```
linkedin_jd/
├── run_pipeline.py              # Main entry point for the entire pipeline
├── scraper/
│   └── simple_login_access.py   # Stealth scraper using undetected-chromedriver
├── analyzer/
│   └── jd_analyzer.py           # AI analysis module (OpenAI integration)
├── templates/
│   └── report.html              # HTML email template
├── data/                        # Local storage for JSON data and artifacts
├── ai/                          # Storage for sensitive AI context/cookies
├── .env.example                 # Example environment variables
└── requirements.txt             # Python dependencies
```

## Prerequisites

- Python 3.10+
- Chrome Browser installed
- OpenAI API Key
- Gmail Account (with App Password for SMTP access)
- LinkedIn Account

## Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/chaeminyoon/python_linkedinJD_email.git
   cd python_linkedinJD_email
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**

   Copy `.env.example` to `.env` and fill in your credentials:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` file:
   ```ini
   # LinkedIn Credentials
   LINKEDIN_EMAIL=your_email@example.com
   LINKEDIN_PASSWORD=your_password

   # OpenAI API
   OPENAI_API_KEY=sk-your-api-key

   # Email Configuration (Gmail)
   SENDER_EMAIL=your_gmail@gmail.com
   SENDER_PASSWORD=your_app_password
   RECIPIENT_EMAIL=recipient@example.com
   ```

## Usage

### Run the Full Pipeline

The easiest way to run the system is using the pipeline script. This handles scraping, analysis, and email notification in one go.

```bash
python run_pipeline.py
```

### Run Individual Components

You can also run components separately for testing or debugging:

**Scraper only:**
```bash
python scraper/simple_login_access.py
```

**Analyzer only (using existing data):**
```bash
python analyzer/jd_analyzer.py
```

**Test Pipeline (Skip Scraping):**
Use existing scraped data to re-run analysis and send email.
```bash
python run_pipeline.py --skip-scrape
```

## Configuration

You can customize search keywords and other settings in `scraper/simple_login_access.py` and `config/settings.py` (if applicable).

Current Search Keywords:
- Data Engineer
- AI Engineer
- Data Scientist

## License

MIT License

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
