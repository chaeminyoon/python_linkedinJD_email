"""
LinkedIn JD Analyzer - Context Manager
Manages pipeline state, agent states, and historical data for trend analysis.
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import DATA_DIR

logger = logging.getLogger(__name__)


class ContextManager:
    """
    Manages the context store for the orchestrator.

    Context includes:
    - Pipeline state (current status, timestamps)
    - Agent states (last run, status, metrics per agent)
    - History (daily stats, skill trends for analysis)
    - Errors (error log with resolution status)
    """

    DEFAULT_CONTEXT = {
        "pipeline_state": {
            "status": "idle",  # idle, running, completed, failed
            "current_agent": None,
            "started_at": None,
            "last_updated": None
        },
        "agent_states": {
            "scraper": {
                "last_run": None,
                "status": "idle",
                "jobs_found": 0,
                "duration_seconds": 0
            },
            "analyzer": {
                "last_run": None,
                "status": "idle",
                "jobs_analyzed": 0,
                "duration_seconds": 0
            },
            "notifier": {
                "last_run": None,
                "status": "idle",
                "email_sent": False,
                "duration_seconds": 0
            }
        },
        "history": {
            "daily_stats": [],
            "skill_trends": {}
        },
        "errors": []
    }

    def __init__(self, context_path: Optional[Path] = None):
        """
        Initialize the ContextManager.

        Args:
            context_path: Path to context.json file. Defaults to DATA_DIR/context.json
        """
        self.context_path = context_path or DATA_DIR / "context.json"
        self.context: Dict[str, Any] = {}
        self._ensure_data_dir()

    def _ensure_data_dir(self) -> None:
        """Ensure the data directory exists."""
        self.context_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now().isoformat()

    def load_context(self) -> Dict[str, Any]:
        """
        Load context from file or create default if not exists.

        Returns:
            Dict containing the loaded or default context
        """
        try:
            if self.context_path.exists():
                with open(self.context_path, 'r', encoding='utf-8') as f:
                    self.context = json.load(f)
                logger.info(f"Context loaded from {self.context_path}")
            else:
                logger.info("No existing context found, creating default")
                self.context = self.DEFAULT_CONTEXT.copy()
                self.save_context()
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse context file: {e}")
            logger.info("Creating new default context")
            self.context = self.DEFAULT_CONTEXT.copy()
            self.save_context()
        except Exception as e:
            logger.error(f"Error loading context: {e}")
            self.context = self.DEFAULT_CONTEXT.copy()

        return self.context

    def save_context(self) -> bool:
        """
        Save current context to file.

        Returns:
            True if save successful, False otherwise
        """
        try:
            self.context["pipeline_state"]["last_updated"] = self._get_timestamp()

            with open(self.context_path, 'w', encoding='utf-8') as f:
                json.dump(self.context, f, indent=2, ensure_ascii=False)
            logger.debug(f"Context saved to {self.context_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save context: {e}")
            return False

    def get_agent_state(self, agent_name: str) -> Dict[str, Any]:
        """
        Get the current state of a specific agent.

        Args:
            agent_name: Name of the agent (scraper, analyzer, notifier)

        Returns:
            Dict containing agent state or empty dict if not found
        """
        return self.context.get("agent_states", {}).get(agent_name, {})

    def update_agent_state(self, agent_name: str, **kwargs) -> None:
        """
        Update the state of a specific agent.

        Args:
            agent_name: Name of the agent
            **kwargs: Key-value pairs to update
        """
        if agent_name not in self.context.get("agent_states", {}):
            logger.warning(f"Unknown agent: {agent_name}")
            return

        self.context["agent_states"][agent_name].update(kwargs)
        self.context["agent_states"][agent_name]["last_run"] = self._get_timestamp()
        logger.debug(f"Updated state for {agent_name}: {kwargs}")

    def update_pipeline_state(self, **kwargs) -> None:
        """
        Update the pipeline state.

        Args:
            **kwargs: Key-value pairs to update (status, current_agent, etc.)
        """
        self.context["pipeline_state"].update(kwargs)
        self.context["pipeline_state"]["last_updated"] = self._get_timestamp()

    def start_pipeline(self) -> None:
        """Mark pipeline as started."""
        self.update_pipeline_state(
            status="running",
            started_at=self._get_timestamp()
        )
        logger.info("Pipeline started")

    def complete_pipeline(self) -> None:
        """Mark pipeline as completed."""
        self.update_pipeline_state(
            status="completed",
            current_agent=None
        )
        logger.info("Pipeline completed")

    def fail_pipeline(self, error_msg: str = None) -> None:
        """Mark pipeline as failed."""
        self.update_pipeline_state(
            status="failed",
            current_agent=None
        )
        if error_msg:
            self.add_error("pipeline", error_msg)
        logger.error(f"Pipeline failed: {error_msg}")

    def update_history(self, daily_stat: Dict[str, Any]) -> None:
        """
        Add daily statistics to history for trend analysis.

        Args:
            daily_stat: Dict containing date, total_jobs, top_skills, etc.
        """
        if "history" not in self.context:
            self.context["history"] = {"daily_stats": [], "skill_trends": {}}

        # Add date if not present
        if "date" not in daily_stat:
            daily_stat["date"] = datetime.now().strftime("%Y-%m-%d")

        # Avoid duplicate entries for the same date
        existing_dates = [s.get("date") for s in self.context["history"]["daily_stats"]]
        if daily_stat["date"] not in existing_dates:
            self.context["history"]["daily_stats"].append(daily_stat)
            logger.info(f"Added daily stats for {daily_stat['date']}")
        else:
            # Update existing entry for today
            for i, stat in enumerate(self.context["history"]["daily_stats"]):
                if stat.get("date") == daily_stat["date"]:
                    self.context["history"]["daily_stats"][i] = daily_stat
                    logger.info(f"Updated daily stats for {daily_stat['date']}")
                    break

        # Update skill trends
        self._update_skill_trends(daily_stat)

        # Keep only last 90 days of history
        self._prune_history(max_days=90)

    def _update_skill_trends(self, daily_stat: Dict[str, Any]) -> None:
        """
        Update skill trends based on daily statistics.

        Args:
            daily_stat: Dict containing skill_frequency data
        """
        skill_freq = daily_stat.get("skill_frequency", {})

        for skill, count in skill_freq.items():
            if skill not in self.context["history"]["skill_trends"]:
                self.context["history"]["skill_trends"][skill] = []

            # Keep last 30 data points per skill
            self.context["history"]["skill_trends"][skill].append(count)
            if len(self.context["history"]["skill_trends"][skill]) > 30:
                self.context["history"]["skill_trends"][skill] = \
                    self.context["history"]["skill_trends"][skill][-30:]

    def _prune_history(self, max_days: int = 90) -> None:
        """
        Remove history entries older than max_days.

        Args:
            max_days: Maximum number of days to keep
        """
        cutoff_date = (datetime.now() - timedelta(days=max_days)).strftime("%Y-%m-%d")

        self.context["history"]["daily_stats"] = [
            stat for stat in self.context["history"]["daily_stats"]
            if stat.get("date", "") >= cutoff_date
        ]

    def get_trend_data(self, days: int = 30) -> Dict[str, Any]:
        """
        Get trend data for the specified number of days.

        Args:
            days: Number of days to retrieve (default 30)

        Returns:
            Dict containing daily_stats and skill_trends for the period
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        daily_stats = [
            stat for stat in self.context.get("history", {}).get("daily_stats", [])
            if stat.get("date", "") >= cutoff_date
        ]

        # Get skill trends (already limited to last 30 entries)
        skill_trends = self.context.get("history", {}).get("skill_trends", {})

        return {
            "daily_stats": daily_stats,
            "skill_trends": skill_trends,
            "period_days": days,
            "data_points": len(daily_stats)
        }

    def add_error(self, agent: str, error: str, resolved: bool = False) -> None:
        """
        Add an error entry to the error log.

        Args:
            agent: Name of the agent that caused the error
            error: Error message
            resolved: Whether the error has been resolved
        """
        error_entry = {
            "timestamp": self._get_timestamp(),
            "agent": agent,
            "error": str(error),
            "resolved": resolved
        }

        if "errors" not in self.context:
            self.context["errors"] = []

        self.context["errors"].append(error_entry)

        # Keep only last 100 errors
        if len(self.context["errors"]) > 100:
            self.context["errors"] = self.context["errors"][-100:]

        logger.error(f"Error logged for {agent}: {error}")

    def resolve_error(self, agent: str) -> None:
        """
        Mark the most recent unresolved error for an agent as resolved.

        Args:
            agent: Name of the agent
        """
        for error in reversed(self.context.get("errors", [])):
            if error.get("agent") == agent and not error.get("resolved"):
                error["resolved"] = True
                logger.info(f"Resolved error for {agent}")
                break

    def get_recent_errors(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most recent errors.

        Args:
            count: Number of errors to retrieve

        Returns:
            List of recent error entries
        """
        return self.context.get("errors", [])[-count:]

    def get_unresolved_errors(self) -> List[Dict[str, Any]]:
        """
        Get all unresolved errors.

        Returns:
            List of unresolved error entries
        """
        return [
            e for e in self.context.get("errors", [])
            if not e.get("resolved")
        ]

    def reset_context(self) -> None:
        """Reset context to default state."""
        self.context = self.DEFAULT_CONTEXT.copy()
        self.save_context()
        logger.info("Context reset to default")
