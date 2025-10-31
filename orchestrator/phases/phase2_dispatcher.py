"""
Phase 2: Dispatcher / Orchestrator

The dispatcher watches for new task specifications and:
1. Creates a dedicated git worktree for the task
2. Creates a trio of agents (Coder, Verifier, Tester)
3. Assigns the spec to these agents
"""

import asyncio
import json
from typing import List, Dict, Any, Optional
from pathlib import Path

from orchestrator.agent_factory import AgentFactory
from orchestrator.db import Database, TaskStatus, AgentStatus
from orchestrator.utils.git_helper import GitHelper
from orchestrator.utils.logger import PipelineLogger


class Dispatcher:
    """
    Phase 2: Watches for new specs and dispatches teams of agents.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        logger: PipelineLogger,
        db: Database,
        git_helper: GitHelper,
        agent_factory: AgentFactory
    ):
        """
        Initialize the dispatcher.

        Args:
            config: Pipeline configuration
            logger: Logger instance
            db: Database instance
            git_helper: Git helper for worktrees
            agent_factory: Agent factory for creating agents
        """
        self.config = config
        self.logger = logger
        self.db = db
        self.git = git_helper
        self.factory = agent_factory

        self.phase2_config = config.get('phase2', {})
        self.base_branch = config['git']['base_branch']

    async def dispatch_task(self, task_id: str) -> bool:
        """
        Dispatch a single task: create worktree and agent team.

        Args:
            task_id: Task ID to dispatch

        Returns:
            True if dispatch successful, False otherwise
        """
        # Get task from database
        task = await self.db.get_task(task_id)

        if not task:
            self.logger.error(f"Task {task_id} not found in database")
            return False

        # Check dependencies
        if self.phase2_config.get('check_dependencies', True):
            if not await self._check_dependencies(task):
                self.logger.warning(
                    f"Task {task_id} has unmet dependencies, skipping for now"
                )
                return False

        self.logger.task_start(task_id, task['title'])

        try:
            # Step 1: Create git worktree
            self.logger.info(f"Creating worktree for {task_id}")
            branch_name, worktree_path = await self.git.create_worktree(
                task_id=task_id,
                base_branch=self.base_branch
            )

            # Update task in database
            await self.db.set_task_branch(task_id, branch_name, worktree_path)

            self.logger.success(f"Created branch {branch_name} at {worktree_path}")

            # Step 2: Load task spec
            spec_path = Path(task['spec_path'])
            with open(spec_path) as f:
                spec = json.load(f)

            # Step 3: Create agent trio
            agents_created = await self._create_agent_trio(
                task_id=task_id,
                spec=spec,
                worktree_path=worktree_path,
                branch_name=branch_name
            )

            if not agents_created:
                self.logger.error(f"Failed to create agents for {task_id}")
                return False

            # Update task status
            await self.db.update_task_status(task_id, TaskStatus.DISPATCHED)

            self.logger.task_end(task_id, success=True)
            return True

        except Exception as e:
            self.logger.error(
                f"Failed to dispatch task {task_id}: {e}",
                exc_info=True
            )
            return False

    async def _check_dependencies(self, task: Dict[str, Any]) -> bool:
        """
        Check if all task dependencies are completed.

        Args:
            task: Task dictionary

        Returns:
            True if all dependencies are met, False otherwise
        """
        dependencies_json = task.get('dependencies')

        if not dependencies_json:
            return True  # No dependencies

        try:
            dependencies = json.loads(dependencies_json) if isinstance(dependencies_json, str) else dependencies_json
        except json.JSONDecodeError:
            self.logger.warning(f"Invalid dependencies JSON for {task['task_id']}")
            return True

        if not dependencies:
            return True

        # Check each dependency
        for dep_task_id in dependencies:
            dep_task = await self.db.get_task(dep_task_id)

            if not dep_task:
                self.logger.warning(f"Dependency {dep_task_id} not found")
                return False

            if dep_task['status'] != TaskStatus.MERGED.value:
                self.logger.info(
                    f"Dependency {dep_task_id} not yet merged "
                    f"(status: {dep_task['status']})"
                )
                return False

        return True

    async def _create_agent_trio(
        self,
        task_id: str,
        spec: Dict[str, Any],
        worktree_path: str,
        branch_name: str
    ) -> bool:
        """
        Create the trio of agents (Coder, Verifier, Tester) for a task.

        Args:
            task_id: Task ID
            spec: Task specification
            worktree_path: Path to git worktree
            branch_name: Git branch name

        Returns:
            True if agents created successfully
        """
        # Agent roles to create
        roles = ['coder', 'verifier', 'tester']

        for role in roles:
            agent_id = f"{role.capitalize()}-{task_id}"

            # Get template for this role
            template_name = self.factory.suggest_template_for_role(role)

            if not template_name:
                self.logger.error(f"No template found for role: {role}")
                return False

            # Create agent in database
            await self.db.create_agent(
                agent_id=agent_id,
                task_id=task_id,
                role=role,
                template_name=template_name
            )

            # Create agent prompt (context injection)
            context = {
                'task_id': task_id,
                'domain': spec.get('domain'),
                'spec': spec,
                'worktree_path': worktree_path,
                'branch_name': branch_name
            }

            # Generate specialized prompt
            agent_prompt = self.factory.create_agent_prompt(
                template_name=template_name,
                context=context,
                role_specialization=self._get_role_specialization(role, spec)
            )

            # Store prompt in agent result (for now)
            # In production, this prompt would be sent to an AI model
            await self.db.update_agent_status(
                agent_id=agent_id,
                status=AgentStatus.CREATED,
                result=json.dumps({'prompt': agent_prompt[:500]})  # Store truncated
            )

            self.logger.agent_created(agent_id, role, task_id)

        return True

    def _get_role_specialization(self, role: str, spec: Dict[str, Any]) -> str:
        """
        Get role-specific specialization instructions.

        Args:
            role: Agent role
            spec: Task specification

        Returns:
            Specialization text
        """
        if role == 'coder':
            files = ', '.join(spec.get('files_scope', []))
            return f"""
            Your focus is implementing the requirements in these files: {files}

            You MUST:
            - Work exclusively in the assigned worktree
            - Follow all requirements precisely
            - Meet all acceptance criteria
            - Write clean, maintainable code
            - Include appropriate error handling
            """

        elif role == 'verifier':
            return f"""
            Your focus is verifying that the implementation matches the specification.

            You MUST check:
            - All requirements are implemented
            - All acceptance criteria are met
            - Only files in scope were modified
            - Code quality is acceptable

            Provide detailed feedback on any deviations from the spec.
            """

        elif role == 'tester':
            return f"""
            Your focus is technical validation: running tests, linting, and builds.

            You MUST:
            - Run all tests in the worktree
            - Check linting and code formatting
            - Run build if applicable
            - Create GitHub issues for failures

            Report GO/NO-GO status with detailed error information if NO-GO.
            """

        return ""

    async def watch_and_dispatch(self, max_iterations: int = 100) -> int:
        """
        Watch for new specs and dispatch them (polling mode).

        Args:
            max_iterations: Maximum number of polling iterations

        Returns:
            Number of tasks dispatched
        """
        watch_interval = self.phase2_config.get('watch_interval', 5)
        max_tasks = self.phase2_config.get('max_tasks', 50)

        dispatched_count = 0

        for iteration in range(max_iterations):
            # Get tasks ready for dispatch
            ready_tasks = await self.db.get_tasks_by_status(TaskStatus.SPEC_READY)

            if not ready_tasks:
                self.logger.debug("No new tasks ready for dispatch")
                break  # No more tasks to dispatch

            # Dispatch tasks
            for task in ready_tasks[:max_tasks - dispatched_count]:
                success = await self.dispatch_task(task['task_id'])

                if success:
                    dispatched_count += 1

                # Small delay between dispatches
                await asyncio.sleep(0.5)

            # Check if we've hit max tasks
            if dispatched_count >= max_tasks:
                self.logger.warning(f"Reached max tasks limit ({max_tasks})")
                break

            # Wait before next iteration
            if iteration < max_iterations - 1:
                await asyncio.sleep(watch_interval)

        return dispatched_count


async def run_phase2(
    config: Dict[str, Any],
    logger: PipelineLogger,
    db: Database,
    git_helper: GitHelper
) -> int:
    """
    Execute Phase 2: Dispatcher.

    Args:
        config: Pipeline configuration
        logger: Logger instance
        db: Database instance
        git_helper: Git helper instance

    Returns:
        Number of tasks dispatched
    """
    logger.phase_start("phase2", "Dispatcher - Creating Worktrees and Agent Teams")

    factory = AgentFactory(config['agents']['templates_path'])

    dispatcher = Dispatcher(
        config=config,
        logger=logger,
        db=db,
        git_helper=git_helper,
        agent_factory=factory
    )

    # Watch and dispatch all ready tasks
    dispatched_count = await dispatcher.watch_and_dispatch()

    logger.success(f"Phase 2 complete: {dispatched_count} tasks dispatched")
    logger.phase_end("phase2", success=True)

    return dispatched_count
