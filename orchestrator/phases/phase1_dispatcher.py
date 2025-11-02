"""
Phase 1: Dispatcher

The dispatcher watches for tasks with cahiers des charges ready and:
1. Creates a dedicated git worktree for each task
2. Updates task status to DISPATCHED

Note: Agents are NOT created here - that's done in Phase 2 (Specialists)
"""

import asyncio
import json
from typing import Dict, Any

from orchestrator.db import Database, TaskStatus
from orchestrator.utils.git_helper import GitHelper
from orchestrator.utils.logger import PipelineLogger


class Dispatcher:
    """
    Phase 1: Watches for tasks with cahiers ready and creates worktrees.

    Note: Does NOT create agents - that's done in Phase 2 (Specialists)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        logger: PipelineLogger,
        db: Database,
        git_helper: GitHelper
    ):
        """
        Initialize the dispatcher.

        Args:
            config: Pipeline configuration
            logger: Logger instance
            db: Database instance
            git_helper: Git helper for worktrees
        """
        self.config = config
        self.logger = logger
        self.db = db
        self.git = git_helper

        self.phase1_config = config.get('phase1', {})
        self.base_branch = config['git']['base_branch']

    async def dispatch_task(self, task_id: str) -> bool:
        """
        Dispatch a single task: create worktree only.

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
        if self.phase1_config.get('check_dependencies', True):
            if not await self._check_dependencies(task):
                self.logger.warning(
                    f"Task {task_id} has unmet dependencies, skipping for now"
                )
                return False

        self.logger.task_start(task_id, task['title'])

        try:
            # Create git worktree
            self.logger.info(f"Creating worktree for {task_id}")
            branch_name, worktree_path = await self.git.create_worktree(
                task_id=task_id,
                base_branch=self.base_branch
            )

            # Update task in database
            await self.db.set_task_branch(task_id, branch_name, worktree_path)

            self.logger.success(f"Created branch {branch_name} at {worktree_path}")

            # Update task status to DISPATCHED
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

    async def watch_and_dispatch(self, max_iterations: int = 100) -> int:
        """
        Watch for tasks with cahiers ready and dispatch them (polling mode).

        Args:
            max_iterations: Maximum number of polling iterations

        Returns:
            Number of tasks dispatched
        """
        watch_interval = self.phase1_config.get('watch_interval', 5)
        max_tasks = self.phase1_config.get('max_tasks', 50)

        dispatched_count = 0

        for iteration in range(max_iterations):
            # Get tasks ready for dispatch (with cahiers ready)
            ready_tasks = await self.db.get_tasks_by_status(TaskStatus.CAHIER_READY)

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


async def run_phase1(
    config: Dict[str, Any],
    logger: PipelineLogger,
    db: Database,
    git_helper: GitHelper
) -> int:
    """
    Execute Phase 1: Dispatcher.

    Creates worktrees for tasks that have cahiers des charges ready.

    Args:
        config: Pipeline configuration
        logger: Logger instance
        db: Database instance
        git_helper: Git helper instance

    Returns:
        Number of tasks dispatched
    """
    logger.phase_start("phase1", "Dispatcher - Creating Worktrees")

    dispatcher = Dispatcher(
        config=config,
        logger=logger,
        db=db,
        git_helper=git_helper
    )

    # Watch and dispatch all ready tasks
    dispatched_count = await dispatcher.watch_and_dispatch()

    logger.success(f"Phase 1 complete: {dispatched_count} tasks dispatched")
    logger.phase_end("phase1", success=True)

    return dispatched_count
