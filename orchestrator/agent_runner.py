"""
LinkedIn JD Analyzer - Agent Runner
Handles agent execution with retry logic, output validation, and logging.
"""
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional, Type, Union

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Status of agent execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class ErrorType(Enum):
    """Types of errors for different retry strategies."""
    RATE_LIMIT = "rate_limit"
    API_ERROR = "api_error"
    NETWORK_ERROR = "network_error"
    VALIDATION_ERROR = "validation_error"
    UNKNOWN = "unknown"


@dataclass
class ExecutionResult:
    """Result of an agent execution."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_type: Optional[ErrorType] = None
    duration_seconds: float = 0.0
    retries_used: int = 0


class BaseAgent(ABC):
    """Abstract base class for all agents."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the agent name."""
        pass

    @abstractmethod
    def run(self, input_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute the agent's main task."""
        pass

    def validate_input(self, input_data: Optional[Dict[str, Any]]) -> bool:
        """Validate input data. Override in subclasses."""
        return True

    def validate_output(self, output_data: Dict[str, Any]) -> bool:
        """Validate output data. Override in subclasses."""
        return True


class AgentRunner:
    """
    Executes agents with retry logic, validation, and logging.

    Features:
    - Configurable retry logic with exponential backoff
    - Input/output validation
    - Execution logging and metrics
    - Error classification for appropriate retry strategies
    """

    # Retry configurations per error type
    RETRY_CONFIG = {
        ErrorType.RATE_LIMIT: {
            "max_retries": 5,
            "base_delay": 60,  # 1 minute
            "max_delay": 300,  # 5 minutes
            "backoff_factor": 2
        },
        ErrorType.API_ERROR: {
            "max_retries": 3,
            "base_delay": 5,
            "max_delay": 30,
            "backoff_factor": 2
        },
        ErrorType.NETWORK_ERROR: {
            "max_retries": 3,
            "base_delay": 30,
            "max_delay": 300,
            "backoff_factor": 2
        },
        ErrorType.VALIDATION_ERROR: {
            "max_retries": 1,
            "base_delay": 0,
            "max_delay": 0,
            "backoff_factor": 1
        },
        ErrorType.UNKNOWN: {
            "max_retries": 2,
            "base_delay": 10,
            "max_delay": 60,
            "backoff_factor": 2
        }
    }

    # Keywords for error classification
    ERROR_KEYWORDS = {
        ErrorType.RATE_LIMIT: ["rate limit", "too many requests", "429", "throttle"],
        ErrorType.API_ERROR: ["api error", "openai", "authentication", "unauthorized", "403"],
        ErrorType.NETWORK_ERROR: ["network", "connection", "timeout", "dns", "socket"],
        ErrorType.VALIDATION_ERROR: ["validation", "invalid", "missing required"],
    }

    def __init__(self):
        """Initialize the AgentRunner."""
        self.execution_logs: list = []

    def classify_error(self, error: Exception) -> ErrorType:
        """
        Classify an error to determine retry strategy.

        Args:
            error: The exception that occurred

        Returns:
            ErrorType classification
        """
        error_str = str(error).lower()

        for error_type, keywords in self.ERROR_KEYWORDS.items():
            if any(kw in error_str for kw in keywords):
                return error_type

        return ErrorType.UNKNOWN

    def calculate_delay(self, error_type: ErrorType, attempt: int) -> float:
        """
        Calculate delay before next retry using exponential backoff.

        Args:
            error_type: Type of error that occurred
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        config = self.RETRY_CONFIG.get(error_type, self.RETRY_CONFIG[ErrorType.UNKNOWN])

        delay = config["base_delay"] * (config["backoff_factor"] ** attempt)
        return min(delay, config["max_delay"])

    def run_with_retry(
        self,
        agent: Union[BaseAgent, Any],
        input_data: Optional[Dict[str, Any]] = None,
        max_retries: int = 3
    ) -> ExecutionResult:
        """
        Run an agent with retry logic.

        Args:
            agent: Agent instance to execute
            input_data: Optional input data to pass to the agent
            max_retries: Maximum number of retry attempts

        Returns:
            ExecutionResult with success status, data, and metrics
        """
        agent_name = getattr(agent, 'name', agent.__class__.__name__)
        start_time = time.time()
        last_error = None
        last_error_type = ErrorType.UNKNOWN
        attempt = 0

        logger.info(f"Starting execution of {agent_name}")

        while attempt <= max_retries:
            try:
                # Validate input if agent supports it
                if hasattr(agent, 'validate_input') and input_data is not None:
                    if not agent.validate_input(input_data):
                        raise ValueError("Input validation failed")

                # Execute the agent
                if hasattr(agent, 'run'):
                    result = agent.run(input_data)
                elif callable(agent):
                    result = agent(input_data) if input_data else agent()
                else:
                    raise TypeError(f"Agent {agent_name} is not callable")

                # Validate output if agent supports it
                if hasattr(agent, 'validate_output'):
                    if not agent.validate_output(result):
                        raise ValueError("Output validation failed")

                duration = time.time() - start_time

                # Log successful execution
                self.log_execution(
                    agent_name=agent_name,
                    result=result,
                    duration=duration,
                    success=True,
                    attempt=attempt
                )

                return ExecutionResult(
                    success=True,
                    data=result,
                    duration_seconds=duration,
                    retries_used=attempt
                )

            except Exception as e:
                last_error = e
                last_error_type = self.classify_error(e)

                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries + 1} failed for {agent_name}: {e}"
                )

                # Check if we should retry based on error type
                error_config = self.RETRY_CONFIG.get(
                    last_error_type,
                    self.RETRY_CONFIG[ErrorType.UNKNOWN]
                )

                if attempt < min(max_retries, error_config["max_retries"]):
                    delay = self.calculate_delay(last_error_type, attempt)
                    logger.info(f"Retrying {agent_name} in {delay:.1f} seconds...")
                    time.sleep(delay)
                    attempt += 1
                else:
                    break

        # All retries exhausted
        duration = time.time() - start_time

        self.log_execution(
            agent_name=agent_name,
            result=None,
            duration=duration,
            success=False,
            attempt=attempt,
            error=str(last_error)
        )

        return ExecutionResult(
            success=False,
            error=str(last_error),
            error_type=last_error_type,
            duration_seconds=duration,
            retries_used=attempt
        )

    def validate_output(self, agent_name: str, result: Dict[str, Any]) -> bool:
        """
        Validate agent output based on agent-specific requirements.

        Args:
            agent_name: Name of the agent
            result: Output data to validate

        Returns:
            True if valid, False otherwise
        """
        if result is None:
            return False

        # Agent-specific validation rules
        validation_rules = {
            "scraper": lambda r: (
                isinstance(r, dict) and
                "jobs" in r and
                isinstance(r.get("jobs"), list)
            ),
            "analyzer": lambda r: (
                isinstance(r, dict) and
                "analyzed_jobs" in r and
                "skill_frequency" in r
            ),
            "notifier": lambda r: (
                isinstance(r, dict) and
                "email_sent" in r
            )
        }

        validator = validation_rules.get(agent_name.lower())
        if validator:
            try:
                return validator(result)
            except Exception as e:
                logger.error(f"Validation error for {agent_name}: {e}")
                return False

        # Default: accept any non-None result
        return True

    def log_execution(
        self,
        agent_name: str,
        result: Optional[Dict[str, Any]],
        duration: float,
        success: bool,
        attempt: int = 0,
        error: Optional[str] = None
    ) -> None:
        """
        Log agent execution details.

        Args:
            agent_name: Name of the executed agent
            result: Execution result (if successful)
            duration: Execution duration in seconds
            success: Whether execution was successful
            attempt: Number of attempts made
            error: Error message (if failed)
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent_name,
            "success": success,
            "duration_seconds": round(duration, 2),
            "attempts": attempt + 1,
            "error": error
        }

        # Add result metrics if available
        if success and result:
            if agent_name.lower() == "scraper":
                log_entry["jobs_found"] = len(result.get("jobs", []))
            elif agent_name.lower() == "analyzer":
                log_entry["jobs_analyzed"] = len(result.get("analyzed_jobs", []))
            elif agent_name.lower() == "notifier":
                log_entry["email_sent"] = result.get("email_sent", False)

        self.execution_logs.append(log_entry)

        # Log to standard logger
        if success:
            logger.info(
                f"[{agent_name}] Completed in {duration:.2f}s "
                f"(attempts: {attempt + 1})"
            )
        else:
            logger.error(
                f"[{agent_name}] Failed after {attempt + 1} attempts: {error}"
            )

    def get_execution_logs(self, agent_name: Optional[str] = None) -> list:
        """
        Get execution logs, optionally filtered by agent.

        Args:
            agent_name: Optional agent name to filter by

        Returns:
            List of execution log entries
        """
        if agent_name:
            return [
                log for log in self.execution_logs
                if log.get("agent", "").lower() == agent_name.lower()
            ]
        return self.execution_logs

    def get_execution_stats(self) -> Dict[str, Any]:
        """
        Get aggregated execution statistics.

        Returns:
            Dict containing execution statistics
        """
        if not self.execution_logs:
            return {"total_executions": 0}

        total = len(self.execution_logs)
        successful = sum(1 for log in self.execution_logs if log.get("success"))
        failed = total - successful

        avg_duration = sum(
            log.get("duration_seconds", 0) for log in self.execution_logs
        ) / total if total > 0 else 0

        avg_attempts = sum(
            log.get("attempts", 1) for log in self.execution_logs
        ) / total if total > 0 else 0

        return {
            "total_executions": total,
            "successful": successful,
            "failed": failed,
            "success_rate": round(successful / total * 100, 1) if total > 0 else 0,
            "average_duration_seconds": round(avg_duration, 2),
            "average_attempts": round(avg_attempts, 2)
        }

    def clear_logs(self) -> None:
        """Clear all execution logs."""
        self.execution_logs = []
        logger.info("Execution logs cleared")
