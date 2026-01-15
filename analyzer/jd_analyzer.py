"""
JD Analyzer Module - AI-powered Job Description Analysis

This module analyzes job descriptions using OpenAI API to extract:
- Required/preferred skills
- Experience requirements
- Education requirements
- Visa sponsorship information
- AI-generated summaries
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from collections import Counter

from openai import OpenAI

# Import configuration
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config.settings import OPENAI_CONFIG, STORAGE_CONFIG

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class JDAnalyzer:
    """
    Job Description Analyzer using OpenAI API.

    Analyzes job postings to extract structured information including
    skills, experience requirements, education, and visa sponsorship.
    """

    def __init__(self, api_key: str | None = None):
        """
        Initialize the JD Analyzer.

        Args:
            api_key: OpenAI API key. If not provided, uses config.
        """
        self.api_key = api_key or OPENAI_CONFIG["api_key"]
        self.model = OPENAI_CONFIG["model"]
        self.max_tokens = OPENAI_CONFIG["max_tokens"]

        # Initialize OpenAI client
        self.client = OpenAI(api_key=self.api_key)

        # File paths from config
        self.jobs_file = STORAGE_CONFIG["jobs_file"]
        self.analysis_file = STORAGE_CONFIG["analysis_file"]

        # Store analysis results
        self.analyzed_jobs: list[dict[str, Any]] = []
        self.skill_frequency: Counter = Counter()
        self.insights: dict[str, Any] = {}

        logger.info("JDAnalyzer initialized with model: %s", self.model)

    def _get_analysis_prompt(self, job_description: str) -> str:
        """
        Generate the analysis prompt for OpenAI.

        Args:
            job_description: The job description text to analyze.

        Returns:
            Formatted prompt string.
        """
        return f"""You are an expert job description analyzer. Analyze the following job description and extract structured information.

JOB DESCRIPTION:
{job_description}

Extract the following information and respond in JSON format:

{{
    "required_skills": ["list of required technical skills and tools"],
    "preferred_skills": ["list of preferred/nice-to-have skills"],
    "experience_years": "required years of experience (e.g., '3-5', '5+', 'entry-level')",
    "education": "education requirements (e.g., 'Bachelor's in CS', 'Master's preferred')",
    "visa_sponsorship": true/false or null if not mentioned,
    "summary": "A concise 2-3 sentence summary of the role and key requirements"
}}

Guidelines:
1. For skills, include programming languages, frameworks, databases, cloud platforms, tools, and methodologies.
2. Distinguish clearly between REQUIRED (must-have) and PREFERRED (nice-to-have) skills.
3. For experience_years, extract the minimum required experience. Use 'entry-level' if none specified.
4. For visa_sponsorship, look for keywords like 'sponsorship', 'work permit', 'visa', 'authorized to work'. Set null if not mentioned.
5. The summary should capture the essence of the role for a job seeker.

Respond ONLY with the JSON object, no additional text."""

    def analyze_single_job(self, job: dict[str, Any]) -> dict[str, Any]:
        """
        Analyze a single job posting using OpenAI API.

        Args:
            job: Job dictionary containing at least 'description' and 'id' fields.

        Returns:
            Analyzed job dictionary with extracted information.
        """
        job_id = job.get("id", "unknown")
        description = job.get("description", "")

        if not description:
            logger.warning("Job %s has no description, skipping analysis", job_id)
            return self._create_empty_analysis(job)

        logger.info("Analyzing job: %s - %s", job_id, job.get("title", "Unknown Title"))

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a job description analyzer. Always respond with valid JSON only."
                    },
                    {
                        "role": "user",
                        "content": self._get_analysis_prompt(description)
                    }
                ],
                max_tokens=self.max_tokens,
                temperature=0.3  # Lower temperature for more consistent extraction
            )

            # Parse the response
            content = response.choices[0].message.content.strip()

            # Handle potential markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            analysis = json.loads(content)

            # Create analyzed job record
            analyzed_job = {
                "job_id": job_id,
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "location": job.get("location", ""),
                "url": job.get("url", ""),
                "posted_date": job.get("posted_date", ""),
                "required_skills": analysis.get("required_skills", []),
                "preferred_skills": analysis.get("preferred_skills", []),
                "experience_years": analysis.get("experience_years", "Not specified"),
                "education": analysis.get("education", "Not specified"),
                "visa_sponsorship": analysis.get("visa_sponsorship"),
                "summary": analysis.get("summary", "")
            }

            logger.info("Successfully analyzed job: %s", job_id)
            return analyzed_job

        except json.JSONDecodeError as e:
            logger.error("Failed to parse OpenAI response for job %s: %s", job_id, e)
            return self._create_empty_analysis(job)
        except Exception as e:
            logger.error("Error analyzing job %s: %s", job_id, e)
            return self._create_empty_analysis(job)

    def _create_empty_analysis(self, job: dict[str, Any]) -> dict[str, Any]:
        """
        Create an empty analysis result for failed analyses.

        Args:
            job: Original job dictionary.

        Returns:
            Analysis dictionary with empty/default values.
        """
        return {
            "job_id": job.get("id", "unknown"),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "url": job.get("url", ""),
            "posted_date": job.get("posted_date", ""),
            "required_skills": [],
            "preferred_skills": [],
            "experience_years": "Not specified",
            "education": "Not specified",
            "visa_sponsorship": None,
            "summary": "Analysis failed"
        }

    def analyze_all_jobs(self) -> list[dict[str, Any]]:
        """
        Analyze all jobs from the jobs.json file.

        Returns:
            List of analyzed job dictionaries.
        """
        # Load jobs from file
        jobs = self._load_jobs()

        if not jobs:
            logger.warning("No jobs found to analyze")
            return []

        logger.info("Starting analysis of %d jobs", len(jobs))

        self.analyzed_jobs = []
        for i, job in enumerate(jobs, 1):
            logger.info("Processing job %d/%d", i, len(jobs))
            analyzed = self.analyze_single_job(job)
            self.analyzed_jobs.append(analyzed)

        logger.info("Completed analysis of %d jobs", len(self.analyzed_jobs))
        return self.analyzed_jobs

    def _load_jobs(self) -> list[dict[str, Any]]:
        """
        Load jobs from the jobs.json file.

        Returns:
            List of job dictionaries.
        """
        if not self.jobs_file.exists():
            logger.error("Jobs file not found: %s", self.jobs_file)
            return []

        try:
            with open(self.jobs_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("jobs", [])
        except json.JSONDecodeError as e:
            logger.error("Failed to parse jobs file: %s", e)
            return []
        except Exception as e:
            logger.error("Error loading jobs file: %s", e)
            return []

    def extract_skills(self, description: str) -> dict[str, list[str]]:
        """
        Extract skills from a job description using pattern matching.

        This is a lightweight alternative to full OpenAI analysis for
        quick skill extraction without API calls.

        Args:
            description: Job description text.

        Returns:
            Dictionary with 'technical' and 'soft' skill lists.
        """
        # Common technical skills to look for
        technical_skills = [
            # Programming Languages
            "Python", "Java", "Scala", "R", "SQL", "JavaScript", "TypeScript",
            "Go", "Rust", "C++", "C#", "Julia", "Bash", "Shell",
            # Data Processing
            "Spark", "PySpark", "Hadoop", "Hive", "Pig", "Flink", "Kafka",
            "Airflow", "Luigi", "Prefect", "Dagster", "dbt",
            # Databases
            "PostgreSQL", "MySQL", "MongoDB", "Cassandra", "Redis", "Elasticsearch",
            "Snowflake", "Redshift", "BigQuery", "Databricks", "Delta Lake",
            # Cloud Platforms
            "AWS", "Azure", "GCP", "Google Cloud", "Amazon Web Services",
            "S3", "EC2", "Lambda", "EMR", "Glue", "Athena",
            # ML/AI
            "TensorFlow", "PyTorch", "Scikit-learn", "Keras", "MLflow",
            "Kubeflow", "SageMaker", "Vertex AI", "Hugging Face",
            # DevOps/Tools
            "Docker", "Kubernetes", "Terraform", "Git", "CI/CD",
            "Jenkins", "GitHub Actions", "GitLab CI", "Ansible",
            # Data Visualization
            "Tableau", "Power BI", "Looker", "Superset", "Grafana",
            # Other
            "REST API", "GraphQL", "Microservices", "ETL", "ELT", "Data Warehouse",
            "Data Lake", "Data Modeling", "Agile", "Scrum"
        ]

        # Normalize description for matching
        desc_lower = description.lower()

        found_skills = []
        for skill in technical_skills:
            # Check for skill mention (case-insensitive)
            if skill.lower() in desc_lower:
                found_skills.append(skill)

        return {
            "technical": found_skills,
            "soft": []  # Could be extended for soft skills
        }

    def calculate_frequency(self) -> dict[str, int]:
        """
        Calculate skill frequency across all analyzed jobs.

        Returns:
            Dictionary mapping skill names to their occurrence counts.
        """
        if not self.analyzed_jobs:
            logger.warning("No analyzed jobs available for frequency calculation")
            return {}

        self.skill_frequency = Counter()

        for job in self.analyzed_jobs:
            # Count required skills
            for skill in job.get("required_skills", []):
                self.skill_frequency[skill] += 1

            # Count preferred skills (with lower weight conceptually, but same count)
            for skill in job.get("preferred_skills", []):
                self.skill_frequency[skill] += 1

        # Convert to regular dict sorted by frequency
        sorted_frequency = dict(
            sorted(self.skill_frequency.items(), key=lambda x: x[1], reverse=True)
        )

        logger.info("Calculated frequency for %d unique skills", len(sorted_frequency))
        return sorted_frequency

    def generate_insights(self) -> dict[str, Any]:
        """
        Generate insights and recommendations based on analysis.

        Returns:
            Dictionary containing insights, trends, and recommendations.
        """
        if not self.analyzed_jobs:
            logger.warning("No analyzed jobs available for insight generation")
            return {}

        # Calculate frequency if not already done
        if not self.skill_frequency:
            self.calculate_frequency()

        total_jobs = len(self.analyzed_jobs)

        # Get top skills (appearing in > 20% of jobs)
        top_skills = [
            skill for skill, count in self.skill_frequency.items()
            if count >= total_jobs * 0.2
        ][:10]  # Limit to top 10

        # Identify trending skills (newer/emerging technologies)
        trending_keywords = [
            "dbt", "Snowflake", "Databricks", "Delta Lake", "Airflow",
            "Kubernetes", "Terraform", "MLOps", "Feature Store", "Lakehouse"
        ]
        trending_skills = [
            skill for skill in self.skill_frequency.keys()
            if any(kw.lower() in skill.lower() for kw in trending_keywords)
        ]

        # Calculate experience distribution
        experience_distribution = Counter()
        for job in self.analyzed_jobs:
            exp = job.get("experience_years", "Not specified")
            experience_distribution[exp] += 1

        # Count visa sponsorship availability
        visa_stats = {
            "available": sum(1 for j in self.analyzed_jobs if j.get("visa_sponsorship") is True),
            "not_available": sum(1 for j in self.analyzed_jobs if j.get("visa_sponsorship") is False),
            "not_mentioned": sum(1 for j in self.analyzed_jobs if j.get("visa_sponsorship") is None)
        }

        # Generate recommendation
        recommendation = self._generate_recommendation(top_skills, trending_skills)

        self.insights = {
            "total_jobs_analyzed": total_jobs,
            "top_skills": top_skills,
            "trending_skills": trending_skills,
            "experience_distribution": dict(experience_distribution),
            "visa_sponsorship_stats": visa_stats,
            "recommendation": recommendation,
            "analysis_date": datetime.now().isoformat()
        }

        logger.info("Generated insights for %d jobs", total_jobs)
        return self.insights

    def _generate_recommendation(
        self,
        top_skills: list[str],
        trending_skills: list[str]
    ) -> str:
        """
        Generate a learning recommendation based on skill analysis.
        Uses OpenAI API for dynamic, personalized strategy generation.

        Args:
            top_skills: Most frequently required skills.
            trending_skills: Emerging/trending skills.

        Returns:
            Recommendation string.
        """
        # Try AI-powered strategy generation first
        try:
            ai_strategy = self._generate_ai_strategy(top_skills, trending_skills)
            if ai_strategy:
                logger.info("Successfully generated AI-powered strategy")
                return ai_strategy
        except Exception as e:
            logger.warning("AI strategy generation failed, using fallback: %s", e)
        
        # Fallback to static recommendation
        return self._generate_fallback_recommendation(top_skills, trending_skills)
    
    def _generate_ai_strategy(
        self,
        top_skills: list[str],
        trending_skills: list[str]
    ) -> str:
        """
        Generate personalized job search strategy using OpenAI API.

        Args:
            top_skills: Most frequently required skills.
            trending_skills: Emerging/trending skills.

        Returns:
            AI-generated strategy string.
        """
        total_jobs = len(self.analyzed_jobs) if self.analyzed_jobs else 0
        
        # 직무 카테고리별 분류
        job_categories = {}
        company_types = []
        experience_counts = {}
        visa_available = 0
        
        if self.analyzed_jobs:
            for job in self.analyzed_jobs:
                # 직무 카테고리 분류
                title = job.get("title", "").lower()
                keyword = job.get("search_keyword", "")
                if keyword:
                    job_categories[keyword] = job_categories.get(keyword, 0) + 1
                
                # 경력 요구사항
                exp = job.get("experience_years", "Not specified")
                experience_counts[exp] = experience_counts.get(exp, 0) + 1
                
                # 회사 정보
                company = job.get("company", "")
                if company:
                    company_types.append(company)
                
                # 비자 스폰서십
                if job.get("visa_sponsorship") == True:
                    visa_available += 1
        
        # 프롬프트 구성
        category_summary = ", ".join([f"{k}: {v}개" for k, v in job_categories.items()]) if job_categories else "정보 없음"
        exp_summary = ", ".join([f"{k}: {v}개" for k, v in experience_counts.items()]) if experience_counts else "정보 없음"
        
        prompt = f"""당신은 캐나다 IT 취업 시장 전문 커리어 컨설턴트입니다. 
다음 오늘자 LinkedIn 채용 데이터 분석 결과를 바탕으로 한국인 구직자를 위한 상세한 취업 전략을 제시해주세요.

📊 [오늘의 캐나다 채용 시장 분석 리포트]

1. 분석된 채용공고: 총 {total_jobs}개
   - 직무별 분포: {category_summary}
   - 경력 요구사항: {exp_summary}
   - 비자 스폰서십 가능: {visa_available}개

2. 가장 많이 요구되는 스킬 (Top 5):
   {', '.join(top_skills[:5]) if top_skills else '정보 없음'}

3. 트렌딩/신기술 스킬:
   {', '.join(trending_skills[:5]) if trending_skills else '정보 없음'}

4. 대표 채용 기업들:
   {', '.join(list(set(company_types))[:5]) if company_types else '정보 없음'}

---

다음 형식으로 구체적이고 실용적인 조언을 제공해주세요:

📌 [시장 현황 요약] (2문장)
오늘 데이터 기반으로 현재 캐나다 Data/AI 채용 시장의 특징을 요약

🎯 [핵심 역량 개발 전략] (3-4문장)
- 반드시 익혀야 할 필수 스킬과 그 이유
- 우선순위별 학습 로드맵 제안

💡 [차별화 포인트] (2-3문장)
- 트렌딩 스킬 기반 경쟁력 확보 방법
- 한국인 지원자의 강점을 살릴 수 있는 전략

📝 [즉시 실행 가능한 액션 플랜] (3가지)
오늘 당장 시작할 수 있는 구체적인 행동 3가지 (포트폴리오, 네트워킹, 학습 등)

⚠️ [주의사항]
비자/영어 관련 현실적인 조언

---
중요: 
- 데이터에 기반한 구체적인 숫자와 예시를 포함해주세요
- 총 400-500자 내외로 작성해주세요
- 한국어로 자연스럽게 작성해주세요"""

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "당신은 캐나다 IT 취업 시장 전문 커리어 컨설턴트입니다. 데이터 기반의 실용적이고 구체적인 조언을 제공합니다. 현실적이면서도 동기부여가 되는 톤으로 작성합니다."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=800,
            temperature=0.7
        )
        
        strategy = response.choices[0].message.content.strip()
        logger.info("AI strategy generated: %d characters", len(strategy))
        return strategy

    def _generate_fallback_recommendation(
        self,
        top_skills: list[str],
        trending_skills: list[str]
    ) -> str:
        """
        Generate a static fallback recommendation when AI generation fails.

        Args:
            top_skills: Most frequently required skills.
            trending_skills: Emerging/trending skills.

        Returns:
            Fallback recommendation string.
        """
        recommendations = []

        # Core skills recommendation
        core_skills = top_skills[:5] if top_skills else []
        if core_skills:
            recommendations.append(
                f"Core skills to master: {', '.join(core_skills)}. "
                "These appear in most job postings and are essential."
            )

        # Trending skills recommendation
        if trending_skills:
            recommendations.append(
                f"Trending skills to learn: {', '.join(trending_skills[:5])}. "
                "These are increasingly in demand and can differentiate your profile."
            )

        # General advice
        recommendations.append(
            "Focus on hands-on projects that demonstrate these skills. "
            "Consider building a portfolio showcasing data pipelines, "
            "cloud deployments, and ML model implementations."
        )

        return " ".join(recommendations)

    def save_analysis(self) -> Path:
        """
        Save analysis results to the analysis.json file.

        Returns:
            Path to the saved analysis file.
        """
        # Ensure frequency and insights are calculated
        if not self.skill_frequency:
            self.calculate_frequency()
        if not self.insights:
            self.generate_insights()

        output = {
            "analyzed_jobs": self.analyzed_jobs,
            "skill_frequency": dict(self.skill_frequency),
            "insights": self.insights,
            "analyzed_at": datetime.now().isoformat()
        }

        # Ensure data directory exists
        self.analysis_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.analysis_file, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        logger.info("Analysis saved to: %s", self.analysis_file)
        return self.analysis_file

    def run(self, input_data: Any = None) -> dict[str, Any]:
        """
        Execute the complete analysis pipeline.

        This method runs the full analysis process:
        1. Load jobs from jobs.json
        2. Analyze each job using OpenAI
        3. Calculate skill frequencies
        4. Generate insights and recommendations
        5. Save results to analysis.json

        Args:
            input_data: Input data from orchestrator (not used, for compatibility)

        Returns:
            Complete analysis results dictionary.
        """
        logger.info("Starting JD analysis pipeline")
        start_time = datetime.now()

        try:
            # Step 1: Analyze all jobs
            self.analyze_all_jobs()

            if not self.analyzed_jobs:
                logger.warning("No jobs were analyzed")
                return {
                    "analyzed_jobs": [],
                    "skill_frequency": {},
                    "insights": {},
                    "analyzed_at": datetime.now().isoformat(),
                    "status": "no_jobs"
                }

            # Step 2: Calculate frequencies
            self.calculate_frequency()

            # Step 3: Generate insights
            self.generate_insights()

            # Step 4: Save results
            self.save_analysis()

            duration = (datetime.now() - start_time).total_seconds()
            logger.info(
                "Analysis pipeline completed in %.2f seconds. "
                "Analyzed %d jobs, found %d unique skills.",
                duration,
                len(self.analyzed_jobs),
                len(self.skill_frequency)
            )

            return {
                "analyzed_jobs": self.analyzed_jobs,
                "skill_frequency": dict(self.skill_frequency),
                "insights": self.insights,
                "analyzed_at": datetime.now().isoformat(),
                "status": "success",
                "duration_seconds": duration
            }

        except Exception as e:
            logger.error("Analysis pipeline failed: %s", e)
            return {
                "analyzed_jobs": self.analyzed_jobs,
                "skill_frequency": dict(self.skill_frequency),
                "insights": self.insights,
                "analyzed_at": datetime.now().isoformat(),
                "status": "error",
                "error": str(e)
            }


# Convenience function for external use
def analyze_jobs(api_key: str | None = None) -> dict[str, Any]:
    """
    Convenience function to run the full analysis pipeline.

    Args:
        api_key: Optional OpenAI API key.

    Returns:
        Analysis results dictionary.
    """
    analyzer = JDAnalyzer(api_key=api_key)
    return analyzer.run()


if __name__ == "__main__":
    # Run analysis when executed directly
    print("Starting JD Analysis...")
    results = analyze_jobs()

    if results.get("status") == "success":
        print(f"\nAnalysis completed successfully!")
        print(f"Jobs analyzed: {len(results.get('analyzed_jobs', []))}")
        print(f"Unique skills found: {len(results.get('skill_frequency', {}))}")

        # Print top 10 skills
        print("\nTop 10 Skills:")
        for i, (skill, count) in enumerate(
            list(results.get('skill_frequency', {}).items())[:10], 1
        ):
            print(f"  {i}. {skill}: {count}")

        # Print insights
        insights = results.get("insights", {})
        if insights:
            print(f"\nRecommendation:")
            print(f"  {insights.get('recommendation', 'N/A')}")
    else:
        print(f"\nAnalysis failed: {results.get('error', 'Unknown error')}")
