"""
LinkedIn JD Analyzer - Main Orchestrator
Central controller that manages all sub-agents and maintains context.
"""
import asyncio
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from config.settings import DATA_DIR, STORAGE_CONFIG
from .context_manager import ContextManager
from .agent_runner import AgentRunner, ExecutionResult, ErrorType

logger = logging.getLogger(__name__)


class PipelineStatus(Enum):
    """Status of the pipeline."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some agents succeeded, some failed


class AgentType(Enum):
    """Types of agents in the pipeline."""
    SCRAPER = "scraper"
    ANALYZER = "analyzer"
    NOTIFIER = "notifier"


class Orchestrator:
    """
    Main orchestrator that manages all sub-agents and coordinates the pipeline.

    Responsibilities:
    - Context management (state, history)
    - Sub-agent execution order control
    - Error handling and retry logic
    - Execution logging and monitoring
    """

    # Default pipeline execution order
    PIPELINE_ORDER = [
        AgentType.SCRAPER,
        AgentType.ANALYZER,
        AgentType.NOTIFIER
    ]

    def __init__(
        self,
        context_path: Optional[Path] = None,
        auto_load_context: bool = True
    ):
        """
        Initialize the Orchestrator.

        Args:
            context_path: Optional path to context.json
            auto_load_context: Whether to automatically load context on init
        """
        self.context_manager = ContextManager(
            context_path or DATA_DIR / "context.json"
        )
        self.agent_runner = AgentRunner()

        # Agent registry - will be populated with actual agent instances
        self._agents: Dict[AgentType, Any] = {}

        # Callbacks for pipeline events
        self._on_agent_start: Optional[Callable] = None
        self._on_agent_complete: Optional[Callable] = None
        self._on_pipeline_complete: Optional[Callable] = None

        if auto_load_context:
            self.context_manager.load_context()

        logger.info("Orchestrator initialized")

    def register_agent(self, agent_type: AgentType, agent_instance: Any) -> None:
        """
        Register an agent instance for the pipeline.

        Args:
            agent_type: Type of agent (SCRAPER, ANALYZER, NOTIFIER)
            agent_instance: The agent instance to register
        """
        self._agents[agent_type] = agent_instance
        logger.info(f"Registered agent: {agent_type.value}")

    def register_agents(
        self,
        scraper: Any = None,
        analyzer: Any = None,
        notifier: Any = None
    ) -> None:
        """
        Register multiple agents at once.

        Args:
            scraper: Scraper agent instance
            analyzer: Analyzer agent instance
            notifier: Notifier agent instance
        """
        if scraper:
            self.register_agent(AgentType.SCRAPER, scraper)
        if analyzer:
            self.register_agent(AgentType.ANALYZER, analyzer)
        if notifier:
            self.register_agent(AgentType.NOTIFIER, notifier)

    def set_callbacks(
        self,
        on_agent_start: Optional[Callable] = None,
        on_agent_complete: Optional[Callable] = None,
        on_pipeline_complete: Optional[Callable] = None
    ) -> None:
        """
        Set callback functions for pipeline events.

        Args:
            on_agent_start: Called when an agent starts
            on_agent_complete: Called when an agent completes
            on_pipeline_complete: Called when pipeline completes
        """
        self._on_agent_start = on_agent_start
        self._on_agent_complete = on_agent_complete
        self._on_pipeline_complete = on_pipeline_complete

    def run_pipeline(
        self,
        skip_agents: Optional[List[AgentType]] = None,
        stop_on_error: bool = True
    ) -> Dict[str, Any]:
        """
        Execute the full pipeline: Scraper -> Analyzer -> Notifier.

        Args:
            skip_agents: Optional list of agents to skip
            stop_on_error: Whether to stop pipeline on agent failure

        Returns:
            Dict containing pipeline results and status
        """
        skip_agents = skip_agents or []
        results: Dict[str, Any] = {
            "status": PipelineStatus.RUNNING.value,
            "started_at": datetime.now().isoformat(),
            "agents": {},
            "errors": []
        }

        # Start pipeline
        self.context_manager.start_pipeline()

        previous_result = None
        failed_agents = []
        completed_agents = []

        try:
            for agent_type in self.PIPELINE_ORDER:
                if agent_type in skip_agents:
                    logger.info(f"Skipping agent: {agent_type.value}")
                    continue

                if agent_type not in self._agents:
                    error_msg = f"Agent not registered: {agent_type.value}"
                    logger.error(error_msg)
                    results["errors"].append({
                        "agent": agent_type.value,
                        "error": error_msg
                    })

                    if stop_on_error:
                        results["status"] = PipelineStatus.FAILED.value
                        self.context_manager.fail_pipeline(error_msg)
                        break
                    continue

                # Execute agent
                agent_result = self.execute_agent(
                    agent_type,
                    input_data=previous_result
                )

                results["agents"][agent_type.value] = {
                    "success": agent_result.success,
                    "duration_seconds": agent_result.duration_seconds,
                    "retries_used": agent_result.retries_used
                }

                if agent_result.success:
                    completed_agents.append(agent_type)
                    previous_result = agent_result.data

                    # Update history with scraper results
                    if agent_type == AgentType.ANALYZER and agent_result.data:
                        self._update_daily_history(agent_result.data)
                else:
                    failed_agents.append(agent_type)
                    results["errors"].append({
                        "agent": agent_type.value,
                        "error": agent_result.error,
                        "error_type": agent_result.error_type.value if agent_result.error_type else None
                    })

                    if stop_on_error:
                        results["status"] = PipelineStatus.FAILED.value
                        self.context_manager.fail_pipeline(agent_result.error)
                        break

            # Determine final status
            if not failed_agents:
                results["status"] = PipelineStatus.COMPLETED.value
                self.context_manager.complete_pipeline()
            elif completed_agents and failed_agents:
                results["status"] = PipelineStatus.PARTIAL.value
            elif not results["status"] == PipelineStatus.FAILED.value:
                results["status"] = PipelineStatus.FAILED.value
                self.context_manager.fail_pipeline("All agents failed")

        except Exception as e:
            logger.exception(f"Pipeline execution error: {e}")
            results["status"] = PipelineStatus.FAILED.value
            results["errors"].append({
                "agent": "pipeline",
                "error": str(e)
            })
            self.context_manager.fail_pipeline(str(e))

        finally:
            results["completed_at"] = datetime.now().isoformat()
            results["completed_agents"] = [a.value for a in completed_agents]
            results["failed_agents"] = [a.value for a in failed_agents]

            # Save context
            self.context_manager.save_context()

            # Call completion callback
            if self._on_pipeline_complete:
                try:
                    self._on_pipeline_complete(results)
                except Exception as e:
                    logger.error(f"Pipeline completion callback error: {e}")

        return results

    def execute_agent(
        self,
        agent_type: Union[AgentType, str],
        input_data: Optional[Dict[str, Any]] = None,
        max_retries: int = 3
    ) -> ExecutionResult:
        """
        Execute a specific agent.

        Args:
            agent_type: The type of agent to execute
            input_data: Optional input data for the agent
            max_retries: Maximum retry attempts

        Returns:
            ExecutionResult with success status and data
        """
        # Convert string to AgentType if needed
        if isinstance(agent_type, str):
            try:
                agent_type = AgentType(agent_type.lower())
            except ValueError:
                return ExecutionResult(
                    success=False,
                    error=f"Unknown agent type: {agent_type}",
                    error_type=ErrorType.VALIDATION_ERROR
                )

        agent_name = agent_type.value

        if agent_type not in self._agents:
            return ExecutionResult(
                success=False,
                error=f"Agent not registered: {agent_name}",
                error_type=ErrorType.VALIDATION_ERROR
            )

        agent = self._agents[agent_type]

        # Update pipeline state
        self.context_manager.update_pipeline_state(current_agent=agent_name)
        self.context_manager.update_agent_state(agent_name, status="running")

        # Call start callback
        if self._on_agent_start:
            try:
                self._on_agent_start(agent_name)
            except Exception as e:
                logger.error(f"Agent start callback error: {e}")

        # Execute with retry
        result = self.agent_runner.run_with_retry(
            agent=agent,
            input_data=input_data,
            max_retries=max_retries
        )

        # Update agent state
        state_update = {
            "status": "completed" if result.success else "failed",
            "duration_seconds": result.duration_seconds
        }

        # Add agent-specific metrics
        if result.success and result.data:
            if agent_type == AgentType.SCRAPER:
                state_update["jobs_found"] = len(result.data.get("jobs", []))
            elif agent_type == AgentType.ANALYZER:
                state_update["jobs_analyzed"] = len(result.data.get("analyzed_jobs", []))
            elif agent_type == AgentType.NOTIFIER:
                state_update["email_sent"] = result.data.get("email_sent", False)

        self.context_manager.update_agent_state(agent_name, **state_update)

        # Log error if failed
        if not result.success:
            self.context_manager.add_error(agent_name, result.error)

        # Call completion callback
        if self._on_agent_complete:
            try:
                self._on_agent_complete(agent_name, result)
            except Exception as e:
                logger.error(f"Agent completion callback error: {e}")

        # Save context
        self.context_manager.save_context()

        return result

    def handle_error(
        self,
        agent_type: Union[AgentType, str],
        error: Exception,
        auto_retry: bool = True
    ) -> Optional[ExecutionResult]:
        """
        Handle an error from an agent execution.

        Args:
            agent_type: The agent that caused the error
            error: The exception that occurred
            auto_retry: Whether to automatically retry the agent

        Returns:
            ExecutionResult if retry was attempted, None otherwise
        """
        if isinstance(agent_type, str):
            try:
                agent_type = AgentType(agent_type.lower())
            except ValueError:
                logger.error(f"Unknown agent type: {agent_type}")
                return None

        agent_name = agent_type.value
        error_type = self.agent_runner.classify_error(error)

        logger.error(f"Handling error for {agent_name}: {error} (type: {error_type.value})")

        # Log error to context
        self.context_manager.add_error(agent_name, str(error))

        # Determine retry strategy based on error type
        retry_config = self.agent_runner.RETRY_CONFIG.get(
            error_type,
            self.agent_runner.RETRY_CONFIG[ErrorType.UNKNOWN]
        )

        if auto_retry and retry_config["max_retries"] > 0:
            logger.info(f"Auto-retrying {agent_name} due to {error_type.value}")

            # Get previous result if available for input
            previous_agent_idx = self.PIPELINE_ORDER.index(agent_type) - 1
            input_data = None

            if previous_agent_idx >= 0:
                # Try to get cached result from previous agent
                previous_agent = self.PIPELINE_ORDER[previous_agent_idx]
                input_data = self._get_cached_result(previous_agent)

            result = self.execute_agent(
                agent_type,
                input_data=input_data,
                max_retries=retry_config["max_retries"]
            )

            if result.success:
                self.context_manager.resolve_error(agent_name)

            return result

        return None

    def _get_cached_result(self, agent_type: AgentType) -> Optional[Dict[str, Any]]:
        """
        Get cached result from a previous agent run.

        Args:
            agent_type: The agent type to get cached result for

        Returns:
            Cached result data or None
        """
        try:
            if agent_type == AgentType.SCRAPER:
                jobs_file = STORAGE_CONFIG.get("jobs_file")
                if jobs_file and jobs_file.exists():
                    import json
                    with open(jobs_file, 'r', encoding='utf-8') as f:
                        return json.load(f)

            elif agent_type == AgentType.ANALYZER:
                analysis_file = STORAGE_CONFIG.get("analysis_file")
                if analysis_file and analysis_file.exists():
                    import json
                    with open(analysis_file, 'r', encoding='utf-8') as f:
                        return json.load(f)

        except Exception as e:
            logger.error(f"Error loading cached result for {agent_type.value}: {e}")

        return None

    def _update_daily_history(self, analysis_data: Dict[str, Any]) -> None:
        """
        Update daily history from analysis results.

        Args:
            analysis_data: Analysis results from analyzer agent
        """
        try:
            daily_stat = {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "total_jobs": len(analysis_data.get("analyzed_jobs", [])),
                "top_skills": analysis_data.get("insights", {}).get("top_skills", []),
                "skill_frequency": analysis_data.get("skill_frequency", {})
            }

            self.context_manager.update_history(daily_stat)
            logger.info("Daily history updated")

        except Exception as e:
            logger.error(f"Error updating daily history: {e}")

    def get_pipeline_status(self) -> Dict[str, Any]:
        """
        Get current pipeline status including all agent states.

        Returns:
            Dict containing pipeline and agent status information
        """
        context = self.context_manager.context

        pipeline_state = context.get("pipeline_state", {})
        agent_states = context.get("agent_states", {})

        # Calculate overall health
        total_agents = len(agent_states)
        healthy_agents = sum(
            1 for state in agent_states.values()
            if state.get("status") in ["completed", "idle"]
        )

        status = {
            "pipeline": {
                "status": pipeline_state.get("status", "unknown"),
                "current_agent": pipeline_state.get("current_agent"),
                "started_at": pipeline_state.get("started_at"),
                "last_updated": pipeline_state.get("last_updated")
            },
            "agents": agent_states,
            "health": {
                "total_agents": total_agents,
                "healthy_agents": healthy_agents,
                "health_percentage": round(healthy_agents / total_agents * 100, 1) if total_agents > 0 else 0
            },
            "registered_agents": [a.value for a in self._agents.keys()],
            "recent_errors": self.context_manager.get_recent_errors(5),
            "execution_stats": self.agent_runner.get_execution_stats()
        }

        return status

    def get_trend_data(self, days: int = 30) -> Dict[str, Any]:
        """
        Get trend data for the specified period.

        Args:
            days: Number of days to retrieve

        Returns:
            Dict containing trend data
        """
        return self.context_manager.get_trend_data(days)

    def reset(self) -> None:
        """Reset the orchestrator and context to initial state."""
        self.context_manager.reset_context()
        self.agent_runner.clear_logs()
        logger.info("Orchestrator reset complete")


async def run_pipeline_async(orchestrator: Orchestrator, **kwargs) -> Dict[str, Any]:
    """
    Run the pipeline asynchronously.

    Args:
        orchestrator: Orchestrator instance
        **kwargs: Arguments to pass to run_pipeline

    Returns:
        Pipeline results
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: orchestrator.run_pipeline(**kwargs))
