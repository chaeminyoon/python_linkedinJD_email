# Sub-Agents 구성 및 역할

## 아키텍처 개요

```
                    ┌─────────────────────────────────────┐
                    │     Agent 0: Orchestrator Agent     │
                    │         (orchestrator.py)           │
                    │                                     │
                    │  - Context 관리 (상태, 히스토리)       │
                    │  - Sub-Agent 실행 순서 제어           │
                    │  - 에러 핸들링 & 재시도               │
                    │  - 실행 로그 & 모니터링               │
                    └──────────────────┬──────────────────┘
                                       │
                                       │ manages
                                       ▼
       ┌───────────────────────────────────────────────────────┐
       │                    Context Store                       │
       │              (data/context.json)                       │
       │  - 현재 파이프라인 상태                                  │
       │  - Agent별 실행 결과                                    │
       │  - 누적 히스토리 (트렌드 분석용)                          │
       └───────────────────────────────────────────────────────┘
                                       │
       ┌───────────────────────┬───────┴───────┬───────────────────────┐
       │                       │               │                       │
       ▼                       ▼               ▼                       ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐   ┌──────────────┐
│   Agent 1    │      │   Agent 2    │      │   Agent 3    │   │   Agent 4    │
│   Scraper    │ ───▶ │   Analyzer   │ ───▶ │   Notifier   │   │   Monitor    │
└──────────────┘      └──────────────┘      └──────────────┘   └──────────────┘
       │                       │                       │               │
       ▼                       ▼                       ▼               ▼
  LinkedIn Jobs           OpenAI API              SMTP Email      Health Check
```

---

## Agent 0: Orchestrator Agent 🎯 (NEW)

### 역할
모든 Sub-Agent를 관리하고 컨텍스트를 유지하는 중앙 제어 Agent

### 담당 파일
- `orchestrator/orchestrator.py` - 메인 오케스트레이터
- `orchestrator/context_manager.py` - 컨텍스트 관리
- `orchestrator/agent_runner.py` - Agent 실행기

### 주요 기능
```python
class Orchestrator:
    def __init__()                    # 컨텍스트 로드 및 초기화
    def run_pipeline()                # 전체 파이프라인 실행
    def execute_agent(agent_name)     # 개별 Agent 실행
    def handle_error(agent, error)    # 에러 처리 및 재시도
    def update_context(result)        # 컨텍스트 업데이트
    def get_pipeline_status()         # 현재 상태 조회

class ContextManager:
    def load_context()                # 저장된 컨텍스트 로드
    def save_context()                # 컨텍스트 저장
    def get_agent_state(agent_name)   # Agent별 상태 조회
    def update_history()              # 히스토리 누적 (트렌드용)
    def get_trend_data(days=30)       # 트렌드 데이터 조회

class AgentRunner:
    def run_with_retry(agent, max_retries=3)  # 재시도 로직
    def validate_output(agent, result)         # 출력 검증
    def log_execution(agent, result, duration) # 실행 로그
```

### Context 구조
```json
{
  "pipeline_state": {
    "status": "running|completed|failed",
    "current_agent": "scraper",
    "started_at": "2024-01-14T07:00:00",
    "last_updated": "2024-01-14T07:05:00"
  },
  "agent_states": {
    "scraper": {
      "last_run": "2024-01-14T07:00:00",
      "status": "completed",
      "jobs_found": 25,
      "duration_seconds": 120
    },
    "analyzer": {
      "last_run": "2024-01-14T07:02:00",
      "status": "completed",
      "jobs_analyzed": 25,
      "duration_seconds": 45
    },
    "notifier": {
      "last_run": "2024-01-14T07:03:00",
      "status": "completed",
      "email_sent": true
    }
  },
  "history": {
    "daily_stats": [
      {
        "date": "2024-01-14",
        "total_jobs": 25,
        "top_skills": ["Python", "SQL", "Spark"]
      }
    ],
    "skill_trends": {
      "Python": [95, 92, 94, 96],
      "SQL": [90, 88, 91, 89]
    }
  },
  "errors": [
    {
      "timestamp": "2024-01-13T07:01:00",
      "agent": "scraper",
      "error": "LinkedIn rate limit",
      "resolved": true
    }
  ]
}
```

### Orchestrator 실행 흐름
```
1. 컨텍스트 로드
   └─▶ 이전 실행 상태 확인

2. 파이프라인 시작
   └─▶ pipeline_state.status = "running"

3. Agent 순차 실행
   ├─▶ Scraper Agent 실행
   │   └─▶ 성공 시 context 업데이트, 실패 시 재시도
   ├─▶ Analyzer Agent 실행
   │   └─▶ Scraper 결과를 input으로 전달
   └─▶ Notifier Agent 실행
       └─▶ Analyzer 결과를 input으로 전달

4. 히스토리 업데이트
   └─▶ 오늘의 통계를 history에 추가

5. 컨텍스트 저장
   └─▶ 다음 실행을 위해 상태 저장
```

### 에러 핸들링 전략
| 에러 유형 | 대응 |
|----------|------|
| LinkedIn 차단 | 대기 후 재시도 (exponential backoff) |
| OpenAI API 실패 | 3회 재시도, 실패 시 이전 분석 결과 사용 |
| 이메일 발송 실패 | 3회 재시도, 실패 시 로컬 저장 후 알림 |
| 네트워크 오류 | 5분 대기 후 재시도 |

### 의존성
- 모든 Sub-Agent 모듈
- logging, asyncio (비동기 실행 옵션)

---

## Agent 1: Scraper Agent 🔍

### 역할
LinkedIn에서 캐나다 Data Engineer/Scientist 채용공고를 자동으로 수집

### 담당 파일
- `scraper/linkedin_scraper.py`

### 주요 기능
```python
class LinkedInScraper:
    def login()              # LinkedIn 로그인
    def search_jobs()        # 채용공고 검색
    def extract_job_details() # JD 상세 정보 추출
    def save_jobs()          # JSON으로 저장
```

### 입력
- 검색 키워드 (Data Engineer, Data Scientist 등)
- 지역 (Canada)
- 시간 필터 (24시간 이내)

### 출력
```json
{
  "jobs": [
    {
      "id": "linkedin_job_id",
      "title": "Senior Data Engineer",
      "company": "Company Name",
      "location": "Toronto, ON",
      "posted_date": "2024-01-14",
      "url": "https://linkedin.com/jobs/...",
      "description": "Full job description...",
      "requirements": ["Python", "SQL", "AWS"]
    }
  ]
}
```

### 의존성
- Selenium, BeautifulSoup, webdriver-manager

---

## Agent 2: Analyzer Agent 🧠

### 역할
수집된 JD를 AI로 분석하여 핵심 역량 및 트렌드 추출

### 담당 파일
- `analyzer/jd_analyzer.py`

### 주요 기능
```python
class JDAnalyzer:
    def analyze_single_job()  # 단일 JD 분석
    def analyze_all_jobs()    # 전체 JD 분석
    def extract_skills()      # 기술 스택 추출
    def calculate_frequency() # 빈도 분석
    def generate_insights()   # 인사이트 생성
```

### 입력
- Scraper Agent가 수집한 jobs.json

### 출력
```json
{
  "analyzed_jobs": [
    {
      "job_id": "...",
      "required_skills": ["Python", "SQL", "Spark"],
      "preferred_skills": ["Airflow", "dbt"],
      "experience_years": "3-5",
      "education": "Bachelor's in CS or related",
      "visa_sponsorship": true,
      "summary": "AI가 생성한 JD 요약"
    }
  ],
  "skill_frequency": {
    "Python": 95,
    "SQL": 90,
    "AWS": 75,
    "Spark": 60
  },
  "insights": {
    "top_skills": ["Python", "SQL", "AWS"],
    "trending_skills": ["dbt", "Snowflake"],
    "recommendation": "Python과 SQL은 필수, Spark 학습 권장"
  }
}
```

### 의존성
- OpenAI API

---

## Agent 3: Notifier Agent 📧

### 역할
분석 결과를 보기 좋은 HTML 리포트로 만들어 이메일 발송

### 담당 파일
- `notifier/email_sender.py`
- `templates/report.html`

### 주요 기능
```python
class EmailSender:
    def create_report()       # HTML 리포트 생성
    def send_email()          # 이메일 발송
    def schedule_daily()      # 매일 아침 스케줄링
```

### 입력
- Analyzer Agent가 생성한 analysis.json

### 출력
- HTML 이메일 리포트 발송

### 리포트 구성
1. **헤더**: 오늘의 캐나다 Data 채용 동향
2. **요약 통계**: 신규 공고 수, 평균 경력 요건
3. **기술 스택 차트**: 빈도 기반 바 그래프
4. **JD 카드**: 각 채용공고 요약 카드
5. **준비 가이드**: AI 추천 학습 우선순위
6. **푸터**: 상세 링크

### 의존성
- smtplib, Jinja2, APScheduler

---

## 데이터 흐름

```
[LinkedIn]
    │
    │ Selenium scraping
    ▼
[jobs.json] ─────────────────────────────┐
    │                                     │
    │ OpenAI analysis                     │
    ▼                                     │
[analysis.json] ──────────────────────┐  │
    │                                  │  │
    │ Jinja2 templating               │  │
    ▼                                  │  │
[HTML Report] ────────────────────┐   │  │
    │                              │   │  │
    │ SMTP send                    │   │  │
    ▼                              │   │  │
[User Email] ◀─────────────────────┴───┴──┘
```

---

## 개발 순서

### Phase 1: 병렬 개발
3개의 Agent를 동시에 개발 가능 (서로 독립적인 인터페이스)

```
┌─────────────┬─────────────┬─────────────┐
│  Agent 1    │  Agent 2    │  Agent 3    │
│  Scraper    │  Analyzer   │  Notifier   │
│             │             │             │
│  [개발중]   │  [개발중]   │  [개발중]   │
└─────────────┴─────────────┴─────────────┘
```

### Phase 2: 통합
main.py에서 3개 Agent 연결

### Phase 3: 테스트
End-to-end 파이프라인 테스트

---

## 인터페이스 계약

### Scraper → Analyzer
```python
# scraper가 저장하는 형식
{
    "jobs": List[JobDict],
    "scraped_at": "2024-01-14T07:00:00",
    "total_count": 25
}
```

### Analyzer → Notifier
```python
# analyzer가 저장하는 형식
{
    "analyzed_jobs": List[AnalyzedJobDict],
    "skill_frequency": Dict[str, int],
    "insights": InsightsDict,
    "analyzed_at": "2024-01-14T07:05:00"
}
```

---

## 환경변수 (각 Agent별)

| Agent | 필요 환경변수 |
|-------|--------------|
| Scraper | LINKEDIN_EMAIL, LINKEDIN_PASSWORD |
| Analyzer | OPENAI_API_KEY |
| Notifier | SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL |
