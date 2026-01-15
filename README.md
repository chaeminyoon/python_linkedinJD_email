# 🇨🇦 LinkedIn JD Analyzer

캐나다 Data Engineer/Scientist 채용공고를 자동으로 수집하고 AI로 분석하여 매일 아침 이메일 리포트를 받아보는 시스템입니다.

## ✨ 주요 기능

- **자동 수집**: LinkedIn에서 최신 Data 채용공고 자동 스크래핑
- **AI 분석**: OpenAI GPT로 기술 스택, 경력 요건, 비자 스폰서십 등 추출
- **트렌드 분석**: 기술 스택 빈도 분석 및 트렌드 추적
- **이메일 리포트**: 보기 좋은 HTML 리포트를 매일 아침 발송
- **Context 관리**: 히스토리 누적으로 장기 트렌드 분석 가능

## 🏗️ 아키텍처

```
┌─────────────────────────────────────┐
│     Agent 0: Orchestrator Agent     │
│  - Context 관리 (상태, 히스토리)       │
│  - Sub-Agent 실행 순서 제어           │
│  - 에러 핸들링 & 재시도               │
└──────────────────┬──────────────────┘
                   │
   ┌───────────────┼───────────────┐
   ▼               ▼               ▼
┌────────┐    ┌────────┐    ┌────────┐
│Scraper │ ─▶ │Analyzer│ ─▶ │Notifier│
│Agent   │    │Agent   │    │Agent   │
└────────┘    └────────┘    └────────┘
```

## 📁 프로젝트 구조

```
linkedin_jd/
├── config/
│   └── settings.py          # 설정 관리
├── orchestrator/
│   ├── orchestrator.py      # 메인 오케스트레이터
│   ├── context_manager.py   # 컨텍스트 관리
│   └── agent_runner.py      # Agent 실행기
├── scraper/
│   └── linkedin_scraper.py  # LinkedIn JD 수집
├── analyzer/
│   └── jd_analyzer.py       # JD 분석 및 역량 추출
├── notifier/
│   └── email_sender.py      # 이메일 발송
├── templates/
│   └── report.html          # 이메일 템플릿
├── data/                    # 데이터 저장소
├── docs/
│   ├── PRD.md              # 제품 요구사항 문서
│   └── SUBAGENTS.md        # Sub-Agent 구성 문서
├── .env.example            # 환경변수 예시
├── requirements.txt        # 의존성
├── main.py                 # 메인 실행 파일
└── scheduler.py            # 스케줄러
```

## 🚀 설치 및 설정

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정

`.env.example`을 `.env`로 복사하고 값을 설정하세요:

```bash
cp .env.example .env
```

```env
# LinkedIn 계정
LINKEDIN_EMAIL=your_linkedin_email@example.com
LINKEDIN_PASSWORD=your_linkedin_password

# OpenAI API
OPENAI_API_KEY=sk-your-openai-api-key

# Gmail 설정 (App Password 사용)
SENDER_EMAIL=your_gmail@gmail.com
SENDER_PASSWORD=your_gmail_app_password
RECIPIENT_EMAIL=recipient@example.com
```

> ⚠️ Gmail App Password 생성: https://support.google.com/accounts/answer/185833

### 3. Chrome WebDriver

Selenium이 자동으로 ChromeDriver를 관리합니다. Chrome 브라우저만 설치되어 있으면 됩니다.

## 💻 사용법

### 전체 파이프라인 실행

```bash
python main.py
```

### 개별 Agent 실행

```bash
python main.py --scrape-only    # 스크래핑만
python main.py --analyze-only   # 분석만
python main.py --notify-only    # 알림만
```

### 상태 조회

```bash
python main.py --status         # 파이프라인 상태
python main.py --trends 30      # 30일 트렌드
```

### 스케줄러 실행 (매일 자동 실행)

```bash
python scheduler.py                 # 기본: 매일 7시 (토론토 시간)
python scheduler.py --hour 8        # 매일 8시
python scheduler.py --run-now       # 즉시 1회 실행 후 스케줄러 시작
python scheduler.py --test          # 테스트 모드 (1분마다)
```

## 📧 리포트 예시

리포트에는 다음 정보가 포함됩니다:

1. **요약 통계**: 신규 공고 수, 분석된 기술 스택 수
2. **기술 스택 빈도**: Python 95%, SQL 90%, Spark 60% ...
3. **준비 가이드**: 필수 스킬, 트렌딩 스킬, AI 추천
4. **채용공고 카드**: 각 JD 요약, 회사, 위치, 요구사항

## ⚙️ 설정 커스터마이징

`config/settings.py`에서 설정을 변경할 수 있습니다:

```python
# 검색 키워드
LINKEDIN_CONFIG = {
    "search_keywords": [
        "Data Engineer",
        "Data Scientist",
        "ML Engineer",
    ],
    "location": "Canada",
    "max_jobs_per_search": 25,
}

# 스케줄러 시간
SCHEDULER_CONFIG = {
    "hour": 7,
    "minute": 0,
    "timezone": "America/Toronto",
}
```

## 🛡️ 주의사항

- LinkedIn 스크래핑은 Rate Limiting이 적용됩니다
- 너무 빈번한 실행은 계정 제한을 받을 수 있습니다
- OpenAI API 사용량에 따른 비용이 발생합니다

## 📝 라이선스

MIT License
