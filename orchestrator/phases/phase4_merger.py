"""
Phase 4: Merger Agent

The merger agent handles merging validated tasks into the main branch.
It includes human validation and interactive conflict resolution.
"""

import asyncio
from typing import Dict, Any, List
from pathlib import Path

from orchestrator.db import Database, TaskStatus
from orchestrator.utils.git_helper import GitHelper
from orchestrator.utils.logger import PipelineLogger


class MergerAgent:
    """Handles merging validated tasks with human oversight"""

    def __init__(
        self,
        config: Dict[str, Any],
        logger: PipelineLogger,
        db: Database,
        git_helper: GitHelper
    ):
        self.config = config
        self.logger = logger
        self.db = db
        self.git = git_helper

        self.phase4_config = config.get('phase4', {})
        self.target_branch = config['git']['base_branch']

    async def merge_task(self, task_id: str, skip_validation: bool = False) -> bool:
        """
        Merge a single task to main branch.

        Args:
            task_id: Task ID to merge
            skip_validation: Skip human validation

        Returns:
            True if merge successful, False otherwise
        """
        task = await self.db.get_task(task_id)

        if not task:
            self.logger.error(f"Task {task_id} not found")
            return False

        # Verify task is ready to merge
        if not await self.db.check_task_ready_for_merge(task_id):
            self.logger.warning(f"Task {task_id} not ready for merge (validations not passed)")
            return False

        self.logger.task_start(task_id, task['title'])

        try:
            # Attempt merge
            self.logger.info(f"Merging branch {task['branch_name']} → {self.target_branch}")

            success, error_msg = await self.git.merge_branch(
                branch_name=task['branch_name'],
                target_branch=self.target_branch
            )

            if not success:
                self.logger.error(f"Merge failed: {error_msg}")

                # Check if it's a conflict
                if "conflict" in error_msg.lower():
                    # SECURITY: No auto-resolution - conflicts always require manual intervention
                    self.logger.merge_conflict(self.git.get_merge_conflicts())

                    # Update task status to MERGE_CONFLICT
                    await self.db.update_task_status(task_id, TaskStatus.MERGE_CONFLICT)

                    # Create conflict report
                    await self._create_conflict_report(task_id, task, error_msg)

                    self.logger.error(
                        f"Task {task_id} has merge conflicts. Manual resolution required. "
                        f"Branch: {task['branch_name']}. "
                        f"Merge was aborted to keep repository clean."
                    )

                    return False
                else:
                    return False

            # Merge successful
            self.logger.success(f"Merged {task_id} successfully")

            # Cleanup
            if self.phase4_config.get('cleanup_after_merge', True):
                await self._cleanup_after_merge(task_id, task['branch_name'])

            # Update database
            await self.db.mark_task_completed(task_id)

            self.logger.task_end(task_id, success=True)

            return True

        except Exception as e:
            self.logger.error(f"Merge failed with exception: {e}", exc_info=True)
            return False

    async def _create_conflict_report(self, task_id: str, task: Dict[str, Any], error_msg: str):
        """
        Create a detailed conflict report for manual resolution.

        Args:
            task_id: Task ID
            task: Task dictionary
            error_msg: Error message from git
        """
        from datetime import datetime
        import json

        # Create conflict reports directory
        report_dir = Path("conflict_reports")
        report_dir.mkdir(exist_ok=True)

        # Prepare report data
        report = {
            "task_id": task_id,
            "title": task['title'],
            "domain": task['domain'],
            "branch_name": task['branch_name'],
            "worktree_path": task['worktree_path'],
            "target_branch": self.target_branch,
            "error_message": error_msg,
            "conflicting_files": self.git.get_merge_conflicts(),
            "timestamp": datetime.now().isoformat(),
            "resolution_instructions": [
                f"1. Navigate to the repository: {self.git.repo_path}",
                f"2. Checkout the feature branch: git checkout {task['branch_name']}",
                f"3. Rebase on {self.target_branch}: git rebase {self.target_branch}",
                "4. Resolve conflicts manually in each file",
                "5. Stage resolved files: git add <file>",
                "6. Continue rebase: git rebase --continue",
                f"7. Force push: git push --force-with-lease origin {task['branch_name']}",
                "8. Re-run phase 5 to attempt merge again"
            ]
        }

        # Save report
        report_path = report_dir / f"{task_id}_conflict.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Conflict report saved to: {report_path}")

    async def _cleanup_after_merge(self, task_id: str, branch_name: str):
        """
        Clean up after successful merge.

        Args:
            task_id: Task ID
            branch_name: Branch name to clean up
        """
        self.logger.info(f"Cleaning up {task_id}")

        try:
            # Remove worktree and branch
            await self.git.cleanup_merged_branch(task_id, branch_name)
            self.logger.success("Cleanup complete")

        except Exception as e:
            self.logger.warning(f"Cleanup failed: {e}")

    async def batch_merge(self, task_ids: List[str]) -> int:
        """
        Merge multiple tasks in sequence.

        Args:
            task_ids: List of task IDs to merge

        Returns:
            Number of successful merges
        """
        successful = 0

        for task_id in task_ids:
            success = await self.merge_task(task_id, skip_validation=False)

            if success:
                successful += 1
            else:
                self.logger.warning(f"Merge failed for {task_id}, continuing with others")

            # Small delay between merges
            await asyncio.sleep(1)

        return successful

    def _prompt_human_validation(self, tasks: List[Dict[str, Any]]) -> bool:
        """
        Prompt human for validation before merging.

        Args:
            tasks: List of tasks to validate

        Returns:
            True if approved, False otherwise
        """
        self.logger.panel(
            f"{len(tasks)} tasks ready for merge",
            title="MERGE VALIDATION REQUIRED",
            color="yellow"
        )

        for task in tasks:
            self.logger.console.print(
                f"  • [cyan]{task['task_id']}[/cyan]: {task['title']} "
                f"[dim]({task['domain']})[/dim]"
            )

        return self.logger.confirm("\nProceed with merge?", default=False)


async def run_phase4(
    config: Dict[str, Any],
    logger: PipelineLogger,
    db: Database,
    git_helper: GitHelper
) -> int:
    """
    Execute Phase 5: Merger with human validation.

    Args:
        config: Pipeline configuration
        logger: Logger instance
        db: Database instance
        git_helper: Git helper instance

    Returns:
        Number of tasks merged successfully
    """
    logger.phase_start("phase4", "Merger - Integration to Main Branch")

    merger = MergerAgent(config, logger, db, git_helper)

    # Get tasks ready for merge
    validated_tasks = await db.get_tasks_by_status(TaskStatus.VALIDATION_PASSED)

    if not validated_tasks:
        logger.info("No tasks ready for merge")
        logger.phase_end("phase4", success=True)
        return 0

    logger.info(f"Found {len(validated_tasks)} tasks ready for merge")

    # Human validation if required
    require_validation = config['phase4'].get('require_human_validation', True)

    if require_validation:
        approved = merger._prompt_human_validation(validated_tasks)

        if not approved:
            logger.warning("Merge cancelled by user")
            logger.phase_end("phase4", success=False)
            return 0

    # Batch merge if enabled
    batch_enabled = config['phase4'].get('batch_merge_enabled', True)
    max_batch_size = config['phase4'].get('max_batch_size', 5)

    if batch_enabled:
        task_ids = [t['task_id'] for t in validated_tasks[:max_batch_size]]
        successful = await merger.batch_merge(task_ids)
    else:
        # Merge one by one
        successful = 0
        for task in validated_tasks:
            if await merger.merge_task(task['task_id']):
                successful += 1

    logger.success(f"Phase 5 complete: {successful}/{len(validated_tasks)} tasks merged")
    logger.phase_end("phase4", success=True)

    return successful
