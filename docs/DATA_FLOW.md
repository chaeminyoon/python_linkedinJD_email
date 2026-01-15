# 📊 Scraping Process - Data Flow Trace

## 전체 아키텍처 (Entry Point to Storage)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ENTRY POINTS (CLI)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  python main.py              → run_full_pipeline()                          │
│  python main.py --scrape-only → run_scrape_only()                           │
│  python scheduler.py         → APScheduler → run_pipeline_job()             │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR LAYER                                   │
│                      orchestrator/orchestrator.py                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  Orchestrator.run_pipeline()                                                 │
│    ├── context_manager.load_context()     # Load previous state              │
│    ├── context_manager.start_pipeline()   # Set status="running"             │
│    │                                                                         │
│    ├── execute_agent(SCRAPER)  ────────────────────────┐                     │
│    │                                                    │                     │
│    ├── execute_agent(ANALYZER) ◄── scraper result ─────┘                     │
│    │                                                    │                     │
│    ├── execute_agent(NOTIFIER) ◄── analyzer result ────┘                     │
│    │                                                                         │
│    ├── context_manager.update_history()   # Save daily stats                 │
│    └── context_manager.save_context()     # Persist to context.json          │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
              [SCRAPER]      [ANALYZER]     [NOTIFIER]
```

---

## 1️⃣ Scraper Agent - 상세 흐름

### 파일 위치
- [scraper/linkedin_scraper.py](scraper/linkedin_scraper.py)

### 실행 흐름

```
LinkedInScraper.run()
│
├── 1. _init_driver()
│   ├── Chrome WebDriver 초기화 (Selenium)
│   ├── Headless 모드 설정
│   ├── Anti-detection 설정 (User-Agent, CDP commands)
│   └── Timeouts 설정 (30초 page load, 10초 implicit wait)
│
├── 2. login()
│   ├── GET https://www.linkedin.com/login
│   ├── 환경변수에서 credentials 로드 (LINKEDIN_EMAIL, LINKEDIN_PASSWORD)
│   ├── 이메일/비밀번호 입력 → 로그인 버튼 클릭
│   └── 로그인 성공 확인 (global-nav 또는 /feed URL 확인)
│
├── 3. search_jobs()
│   ├── 각 키워드에 대해 반복 (Data Engineer, Data Scientist, ML Engineer)
│   │
│   ├── URL 구성:
│   │   https://www.linkedin.com/jobs/search/
│   │   ?keywords=Data%20Engineer
│   │   &location=Canada
│   │   &f_TPR=r86400          # 24시간 필터
│   │   &sortBy=DD             # 최신순 정렬
│   │
│   ├── _collect_jobs_on_page()
│   │   ├── 스크롤 다운 (lazy loading 트리거)
│   │   ├── CSS Selector: "li.scaffold-layout__list-item"
│   │   └── 각 카드에서 _extract_job_card_info() 호출
│   │
│   └── _go_to_next_page() → 다음 페이지 반복
│
├── 4. extract_job_details(job) [각 job에 대해]
│   ├── GET https://www.linkedin.com/jobs/view/{job_id}
│   ├── "See more" 버튼 클릭 (전체 description 표시)
│   ├── description 추출 (.jobs-description__content)
│   ├── _extract_posted_date() → 상대 날짜 파싱
│   └── _extract_requirements() → 기술 스택 키워드 매칭
│
├── 5. save_jobs()
│   └── JSON 파일 저장 → data/jobs.json
│
└── 6. driver.quit()
    └── WebDriver 종료
```

### 추출 데이터 구조

```python
# _extract_job_card_info() 반환값
{
    "job_id": "3812345678",           # LinkedIn 고유 ID
    "title": "Senior Data Engineer",  # 직무명
    "company": "Company Name",         # 회사명
    "location": "Toronto, ON",         # 위치
    "url": "https://linkedin.com/jobs/view/3812345678"
}

# extract_job_details() 추가 데이터
{
    ...
    "description": "Full job description text...",
    "posted_date": "2024-01-14",
    "requirements": ["Python", "SQL", "Spark", "AWS"],
    "scraped_at": "2024-01-14T07:05:00"
}
```

### 출력 파일: `data/jobs.json`

```json
{
  "jobs": [
    {
      "job_id": "3812345678",
      "title": "Senior Data Engineer",
      "company": "Company Name",
      "location": "Toronto, ON",
      "url": "https://linkedin.com/jobs/view/3812345678",
      "description": "We are looking for...",
      "posted_date": "2024-01-14",
      "requirements": ["Python", "SQL", "Spark"],
      "scraped_at": "2024-01-14T07:05:00"
    },
    ...
  ],
  "scraped_at": "2024-01-14T07:10:00",
  "total_count": 25
}
```

---

## 2️⃣ Analyzer Agent - 상세 흐름

### 파일 위치
- [analyzer/jd_analyzer.py](analyzer/jd_analyzer.py)

### 실행 흐름

```
JDAnalyzer.run()
│
├── 1. jobs.json 로드
│   └── data/jobs.json → List[Dict]
│
├── 2. analyze_all_jobs()
│   └── 각 job에 대해 analyze_single_job() 호출
│       │
│       ├── OpenAI API 호출 (gpt-4o-mini)
│       │   ├── Prompt: JD에서 구조화된 정보 추출
│       │   └── Response: JSON 형식 (skills, experience, education)
│       │
│       └── 분석 결과:
│           ├── required_skills: ["Python", "SQL", "Spark"]
│           ├── preferred_skills: ["Airflow", "dbt"]
│           ├── experience_years: "3-5"
│           ├── education: "Bachelor's in CS"
│           ├── visa_sponsorship: true/false
│           └── summary: "AI 생성 요약"
│
├── 3. calculate_frequency()
│   └── 전체 JD에서 기술 스택 등장 빈도 계산
│       {"Python": 95, "SQL": 90, "AWS": 75, ...}
│
├── 4. generate_insights()
│   ├── top_skills: 상위 10개 기술
│   ├── trending_skills: 신규 트렌드 기술
│   ├── experience_distribution: 경력 분포
│   ├── visa_sponsorship_stats: 비자 통계
│   └── recommendation: AI 학습 추천
│
└── 5. save_analysis()
    └── JSON 파일 저장 → data/analysis.json
```

### 출력 파일: `data/analysis.json`

```json
{
  "analyzed_jobs": [...],
  "skill_frequency": {
    "Python": 95,
    "SQL": 90,
    "AWS": 75,
    "Spark": 60
  },
  "insights": {
    "total_jobs_analyzed": 25,
    "top_skills": ["Python", "SQL", "AWS"],
    "trending_skills": ["dbt", "Snowflake"],
    "recommendation": "Python과 SQL은 필수, Spark 학습 권장"
  },
  "analyzed_at": "2024-01-14T07:15:00"
}
```

---

## 3️⃣ Notifier Agent - 상세 흐름

### 파일 위치
- [notifier/email_sender.py](notifier/email_sender.py)
- [templates/report.html](templates/report.html)

### 실행 흐름

```
EmailSender.run()
│
├── 1. _init_auth_method()
│   ├── OAuth 토큰 확인 (data/gmail_token.pickle)
│   │   ├── 있으면 → Gmail API 사용
│   │   └── 없으면 → SMTP fallback
│   │
│   └── Gmail OAuth 인증 또는 SMTP 설정
│
├── 2. load_analysis()
│   └── data/analysis.json 로드
│
├── 3. create_report()
│   ├── Jinja2 템플릿 로드 (templates/report.html)
│   ├── _prepare_template_data()
│   │   ├── skill_chart_data: 기술 스택 차트 데이터
│   │   ├── jobs: 분석된 채용공고 목록
│   │   └── insights: 인사이트 및 추천
│   │
│   └── HTML 렌더링 → self.report_html
│
├── 4. save_report()
│   └── data/report_2024-01-14.html (로컬 백업)
│
└── 5. send_email()
    ├── OAuth 방식: _send_email_oauth()
    │   ├── MIMEMultipart 메시지 생성
    │   ├── base64 인코딩
    │   └── Gmail API: users().messages().send()
    │
    └── SMTP 방식: _send_email_smtp()
        ├── SMTP 연결 (smtp.gmail.com:587)
        ├── STARTTLS 암호화
        ├── 로그인 (App Password)
        └── 메시지 전송
```

### 출력
- 이메일 발송 → 사용자 받은편지함
- 로컬 백업 → `data/report_YYYY-MM-DD.html`

---

## 4️⃣ Context Manager - 상태 저장

### 파일 위치
- [orchestrator/context_manager.py](orchestrator/context_manager.py)

### 저장 파일: `data/context.json`

```json
{
  "pipeline_state": {
    "status": "completed",
    "current_agent": null,
    "started_at": "2024-01-14T07:00:00",
    "last_updated": "2024-01-14T07:20:00"
  },
  "agent_states": {
    "scraper": {
      "last_run": "2024-01-14T07:00:00",
      "status": "completed",
      "jobs_found": 25,
      "duration_seconds": 300
    },
    "analyzer": {
      "last_run": "2024-01-14T07:05:00",
      "status": "completed",
      "jobs_analyzed": 25,
      "duration_seconds": 120
    },
    "notifier": {
      "last_run": "2024-01-14T07:07:00",
      "status": "completed",
      "email_sent": true,
      "duration_seconds": 5
    }
  },
  "history": {
    "daily_stats": [
      {
        "date": "2024-01-14",
        "total_jobs": 25,
        "top_skills": ["Python", "SQL", "Spark"],
        "skill_frequency": {...}
      }
    ],
    "skill_trends": {
      "Python": [95, 92, 94, 96],
      "SQL": [90, 88, 91, 89]
    }
  },
  "errors": []
}
```

---

## 📁 전체 데이터 저장 구조

```
data/
├── jobs.json           # Scraper 출력 (수집된 JD)
├── analysis.json       # Analyzer 출력 (분석 결과)
├── context.json        # Orchestrator 상태 (파이프라인 상태, 히스토리)
├── gmail_token.pickle  # OAuth 토큰 (선택)
└── report_YYYY-MM-DD.html  # 이메일 백업 (선택)
```

---

## 🔄 전체 시퀀스 다이어그램

```
User/Scheduler    main.py      Orchestrator    Scraper         Analyzer        Notifier
     │               │               │             │               │               │
     │──run───────▶│               │             │               │               │
     │               │──setup()───▶│             │               │               │
     │               │               │             │               │               │
     │               │◀──ready──────│             │               │               │
     │               │               │             │               │               │
     │               │──run_pipeline()───────────▶│               │               │
     │               │               │             │               │               │
     │               │               │──run()────▶│               │               │
     │               │               │             │──login()───▶LinkedIn        │
     │               │               │             │◀──session────│               │
     │               │               │             │──search()──▶LinkedIn        │
     │               │               │             │◀──jobs───────│               │
     │               │               │             │──details()─▶LinkedIn        │
     │               │               │             │◀──JD─────────│               │
     │               │               │             │               │               │
     │               │               │◀─jobs.json─│               │               │
     │               │               │             │               │               │
     │               │               │──────────────────run()────▶│               │
     │               │               │                             │──API───────▶OpenAI
     │               │               │                             │◀──analysis──│
     │               │               │                             │               │
     │               │               │◀──────analysis.json────────│               │
     │               │               │                             │               │
     │               │               │───────────────────────────────run()──────▶│
     │               │               │                                            │
     │               │               │                                   ┌────────┴────────┐
     │               │               │                                   │ OAuth or SMTP?  │
     │               │               │                                   └────────┬────────┘
     │               │               │                                            │
     │               │               │                                   Gmail API/SMTP
     │               │               │                                            │
     │               │               │◀──────────────email_sent───────────────────│
     │               │               │                                            │
     │               │◀──result──────│                                            │
     │◀──done────────│               │                                            │
     │               │               │                                            │
```

---

## ⚠️ 현재 구조의 특징

### 데이터베이스 없음
- 모든 데이터는 **JSON 파일**로 저장됨
- 간단한 파일 기반 저장소 (SQLite/PostgreSQL 없음)

### 프론트엔드 없음
- CLI 기반 실행
- 결과는 **이메일**로 전달

### 확장 가능성
데이터베이스와 프론트엔드를 추가하려면:
1. **DB 추가**: `storage/database.py` 모듈 생성, SQLAlchemy 사용
2. **API 추가**: FastAPI로 REST API 제공
3. **Frontend 추가**: React/Next.js로 대시보드 구축
