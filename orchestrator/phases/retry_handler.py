"""
Retry Handler - Manages the correction loop for failed validations.

When a task fails validation (Phase 4), this handler:
1. Retrieves detailed feedback
2. Checks retry count
3. Reinjects the task into Phase 3 with feedback for correction
4. Limits retries to prevent infinite loops
"""

import asyncio
import json
from typing import Dict, Any, Optional

from orchestrator.db import Database, TaskStatus
from orchestrator.utils.logger import PipelineLogger


class RetryHandler:
    """Handles retry logic for failed validations"""

    def __init__(
        self,
        config: Dict[str, Any],
        logger: PipelineLogger,
        db: Database
    ):
        """
        Initialize retry handler.

        Args:
            config: Pipeline configuration
            logger: Logger instance
            db: Database instance
        """
        self.config = config
        self.logger = logger
        self.db = db

        self.error_config = config.get('error_handling', {})
        self.max_retries = self.error_config.get('max_retries', 3)
        self.enable_retry = self.error_config.get('enable_retry_loop', True)

    async def process_failed_tasks(self) -> int:
        """
        Process all tasks that failed validation and prepare them for retry.

        Returns:
            Number of tasks prepared for retry
        """
        if not self.enable_retry:
            self.logger.info("Retry loop disabled in configuration")
            return 0

        self.logger.info("Processing failed validations for retry...")

        # Get all failed tasks
        failed_tasks = await self.db.get_tasks_by_status(TaskStatus.VALIDATION_FAILED)

        if not failed_tasks:
            self.logger.info("No failed tasks to retry")
            return 0

        retry_count = 0

        for task in failed_tasks:
            task_id = task['task_id']

            # Check retry count
            current_retries = await self.db.get_retry_count(task_id)

            if current_retries >= self.max_retries:
                # Max retries reached - mark as permanently failed
                self.logger.error(
                    f"Task {task_id} reached max retries ({self.max_retries}). "
                    f"Marking as FAILED."
                )

                await self.db.update_task_status(task_id, TaskStatus.FAILED)
                continue

            # Retrieve validation feedback
            validations = await self.db.get_validations_for_task(task_id)

            if not validations:
                self.logger.warning(f"No validation records found for {task_id}")
                continue

            # Build detailed feedback
            feedback = await self._build_feedback(task_id, validations)

            # Increment retry count and store feedback
            await self.db.increment_retry(task_id, json.dumps(feedback))

            # Reset to CODE_DONE to put back in Phase 3 queue
            await self.db.update_task_status(task_id, TaskStatus.CODE_DONE)

            retry_count += 1

            self.logger.warning(
                f"Task {task_id} prepared for retry {current_retries + 1}/{self.max_retries}. "
                f"Feedback: {len(feedback['issues'])} issues identified."
            )

        return retry_count

    async def _build_feedback(
        self,
        task_id: str,
        validations: list
    ) -> Dict[str, Any]:
        """
        Build detailed feedback from validation results.

        Args:
            task_id: Task ID
            validations: List of validation records

        Returns:
            Structured feedback dictionary
        """
        feedback = {
            'task_id': task_id,
            'retry_reason': 'validation_failed',
            'issues': []
        }

        for validation in validations:
            if validation['status'] == 'no_go':
                issue = {
                    'validator_type': validation['validator_type'],
                    'message': validation['message'],
                    'timestamp': validation['created_at']
                }

                # Parse details if available
                if validation['details']:
                    try:
                        details = json.loads(validation['details'])
                        issue['details'] = details
                    except json.JSONDecodeError:
                        pass

                feedback['issues'].append(issue)

        # Add summary
        feedback['summary'] = self._generate_feedback_summary(feedback['issues'])

        return feedback

    def _generate_feedback_summary(self, issues: list) -> str:
        """
        Generate human-readable summary of issues.

        Args:
            issues: List of validation issues

        Returns:
            Summary string
        """
        logic_issues = [i for i in issues if i['validator_type'] == 'logic']
        tech_issues = [i for i in issues if i['validator_type'] == 'tech']

        summary_parts = []

        if logic_issues:
            summary_parts.append(
                f"Logic validation failed: {len(logic_issues)} requirement(s) not met"
            )

        if tech_issues:
            summary_parts.append(
                f"Technical validation failed: {len(tech_issues)} test(s) failed"
            )

        return ". ".join(summary_parts) if summary_parts else "Unknown validation failure"


async def run_retry_handler(
    config: Dict[str, Any],
    logger: PipelineLogger,
    db: Database
) -> int:
    """
    Execute retry handler to process failed tasks.

    This should be called between Phase 4 and Phase 3 in the pipeline loop.

    Args:
        config: Pipeline configuration
        logger: Logger instance
        db: Database instance

    Returns:
        Number of tasks prepared for retry
    """
    logger.info("🔄 Retry Handler - Processing Failed Validations")

    handler = RetryHandler(config, logger, db)

    retry_count = await handler.process_failed_tasks()

    if retry_count > 0:
        logger.success(f"Prepared {retry_count} tasks for retry")
    else:
        logger.info("No tasks to retry")

    return retry_count
