"""
Phase 3: Coder Agents

Coder agents work in parallel, each in their dedicated worktree,
implementing the requirements specified in their task spec.
"""

import asyncio
import json
from typing import Dict, Any, List
from pathlib import Path

from orchestrator.db import Database, TaskStatus, AgentStatus
from orchestrator.utils.git_helper import GitHelper
from orchestrator.utils.logger import PipelineLogger


class CoderAgent:
    """A coder agent that implements a task specification"""

    def __init__(
        self,
        task_id: str,
        agent_id: str,
        spec: Dict[str, Any],
        worktree_path: str,
        branch_name: str,
        config: Dict[str, Any],
        logger: PipelineLogger,
        db: Database,
        git_helper: GitHelper
    ):
        """Initialize coder agent"""
        self.task_id = task_id
        self.agent_id = agent_id
        self.spec = spec
        self.worktree_path = worktree_path
        self.branch_name = branch_name
        self.config = config
        self.logger = logger
        self.db = db
        self.git = git_helper

    async def code(self) -> bool:
        """
        Implement the task specification.

        Returns:
            True if coding successful, False otherwise
        """
        # Check if this is a retry with feedback
        retry_count = await self.db.get_retry_count(self.task_id)
        last_feedback = await self.db.get_last_feedback(self.task_id)

        if retry_count > 0 and last_feedback:
            self.logger.agent_working(
                self.agent_id,
                f"Implementing task specification (retry {retry_count}/3 with feedback)"
            )
        else:
            self.logger.agent_working(self.agent_id, "Implementing task specification")

        # Update agent status
        await self.db.update_agent_status(self.agent_id, AgentStatus.WORKING)

        try:
            # TODO: In production, invoke AI model to write code with feedback
            # For now, simulate coding
            success = await self._simulate_coding(last_feedback)

            if success:
                # Commit changes
                await self._commit_changes()

                # Push branch
                await self.git.push_branch(self.branch_name)

                # Update statuses
                await self.db.update_agent_status(
                    self.agent_id,
                    AgentStatus.COMPLETED,
                    result="Code implementation completed"
                )

                await self.db.update_task_status(self.task_id, TaskStatus.CODE_DONE)

                self.logger.agent_completed(self.agent_id)
                return True
            else:
                await self.db.update_agent_status(
                    self.agent_id,
                    AgentStatus.ERROR,
                    error_message="Failed to implement code"
                )
                return False

        except Exception as e:
            self.logger.error(f"Coder agent {self.agent_id} failed: {e}", exc_info=True)

            await self.db.update_agent_status(
                self.agent_id,
                AgentStatus.ERROR,
                error_message=str(e)
            )

            return False

    async def _simulate_coding(self, feedback_json: str = None) -> bool:
        """
        Simulate code implementation.

        In production, this would invoke an AI model to write actual code,
        with feedback from previous attempts injected into the prompt.

        Args:
            feedback_json: JSON feedback from failed validation (if retry)
        """
        # Simulate work
        await asyncio.sleep(2)

        # Create a simple placeholder file in the worktree
        worktree = Path(self.worktree_path)

        # Build implementation content
        content_parts = [
            f"Task: {self.spec['title']}",
            f"Domain: {self.spec['domain']}",
            "",
            "Requirements implemented:",
            *[f'- {req}' for req in self.spec['requirements']],
            "",
            "Acceptance criteria met:",
            *[f'- {criterion}' for criterion in self.spec['acceptance_criteria']],
        ]

        # If this is a retry, add feedback section
        if feedback_json:
            try:
                feedback = json.loads(feedback_json)
                content_parts.extend([
                    "",
                    "=== RETRY ATTEMPT ===",
                    f"Retry reason: {feedback.get('retry_reason', 'unknown')}",
                    f"Previous issues: {len(feedback.get('issues', []))}",
                    "",
                    "Feedback from previous attempt:",
                    feedback.get('summary', 'No summary available'),
                    "",
                    "Corrections applied:"
                ])

                for i, issue in enumerate(feedback.get('issues', []), 1):
                    content_parts.append(
                        f"  {i}. Fixed {issue['validator_type']} issue: {issue['message']}"
                    )

            except json.JSONDecodeError:
                content_parts.extend([
                    "",
                    "=== RETRY (malformed feedback) ===",
                ])

        content_parts.extend([
            "",
            "This is a simulated implementation.",
            "In production, real code would be written here by an AI model.",
            "The feedback would be injected into the AI prompt to guide corrections."
        ])

        # Create a sample implementation file
        sample_file = worktree / "implementation.txt"
        sample_file.write_text("\n".join(content_parts))

        return True

    async def _commit_changes(self):
        """Commit code changes"""
        commit_template = self.config['phase3'].get('commit_message_template', '{title}')

        commit_message = commit_template.format(
            title=self.spec['title'],
            description=self.spec['description'],
            task_id=self.task_id,
            domain=self.spec['domain']
        )

        try:
            commit_sha = await self.git.commit_changes(
                worktree_path=self.worktree_path,
                message=commit_message
            )

            self.logger.success(f"Committed changes: {commit_sha[:8]}")

        except ValueError as e:
            if "No changes to commit" in str(e):
                self.logger.warning("No changes to commit")
            else:
                raise


async def run_phase3(
    config: Dict[str, Any],
    logger: PipelineLogger,
    db: Database,
    git_helper: GitHelper
) -> int:
    """
    Execute Phase 3: Coder Agents (parallel execution).

    Args:
        config: Pipeline configuration
        logger: Logger instance
        db: Database instance
        git_helper: Git helper instance

    Returns:
        Number of tasks coded successfully
    """
    logger.phase_start("phase3", "Coder Agents - Implementation")

    # Get dispatched tasks
    dispatched_tasks = await db.get_tasks_by_status(TaskStatus.DISPATCHED)

    if not dispatched_tasks:
        logger.info("No tasks ready for coding")
        logger.phase_end("phase3", success=True)
        return 0

    logger.info(f"Found {len(dispatched_tasks)} tasks ready for coding")

    # Create coder agents
    coders = []

    for task in dispatched_tasks:
        # Load spec
        spec_path = Path(task['spec_path'])
        with open(spec_path) as f:
            spec = json.load(f)

        # Get coder agent ID
        agents = await db.get_agents_for_task(task['task_id'])
        coder_agent = next((a for a in agents if a['role'] == 'coder'), None)

        if not coder_agent:
            logger.error(f"No coder agent found for {task['task_id']}")
            continue

        # Create coder instance
        coder = CoderAgent(
            task_id=task['task_id'],
            agent_id=coder_agent['agent_id'],
            spec=spec,
            worktree_path=task['worktree_path'],
            branch_name=task['branch_name'],
            config=config,
            logger=logger,
            db=db,
            git_helper=git_helper
        )

        coders.append(coder)

    # Run coders in parallel
    max_parallel = config['phase3'].get('max_parallel_coders', 3)
    semaphore = asyncio.Semaphore(max_parallel)

    async def code_with_semaphore(coder):
        async with semaphore:
            return await coder.code()

    results = await asyncio.gather(*[code_with_semaphore(c) for c in coders])

    successful = sum(1 for r in results if r)

    logger.success(f"Phase 3 complete: {successful}/{len(coders)} tasks coded successfully")
    logger.phase_end("phase3", success=True)

    return successful
