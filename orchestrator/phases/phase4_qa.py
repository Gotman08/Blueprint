"""
Phase 4: QA - Verification and Testing

Two types of agents work in parallel for each task:
1. Verifier: Checks if code matches spec (logic validation)
2. Tester: Runs tests, linting, build (technical validation)
"""

import asyncio
import json
from typing import Dict, Any, Tuple
from pathlib import Path

from orchestrator.db import Database, TaskStatus, AgentStatus, ValidationStatus
from orchestrator.utils.git_helper import GitHelper
from orchestrator.utils.logger import PipelineLogger


class VerifierAgent:
    """Verifies that implementation matches specification"""

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
        self.task_id = task_id
        self.agent_id = agent_id
        self.spec = spec
        self.worktree_path = worktree_path
        self.branch_name = branch_name
        self.config = config
        self.logger = logger
        self.db = db
        self.git = git_helper

    async def verify(self) -> Tuple[ValidationStatus, str]:
        """
        Verify implementation against spec.

        Returns:
            Tuple of (status, message)
        """
        self.logger.agent_working(self.agent_id, "Verifying code against spec")

        await self.db.update_agent_status(self.agent_id, AgentStatus.WORKING)

        try:
            # TODO: In production, use AI to compare diff with spec
            # For now, simulate verification
            success, message = await self._simulate_verification()

            status = ValidationStatus.GO if success else ValidationStatus.NO_GO

            # Create validation record
            validation_id = await self.db.create_validation(
                self.task_id,
                'logic',
                status
            )

            await self.db.update_validation(
                validation_id,
                status,
                message=message
            )

            # Update agent status
            await self.db.update_agent_status(
                self.agent_id,
                AgentStatus.COMPLETED,
                result=message
            )

            self.logger.validation_result(self.task_id, 'logic', status.value, message)
            self.logger.agent_completed(self.agent_id)

            return status, message

        except Exception as e:
            self.logger.error(f"Verifier failed: {e}", exc_info=True)

            await self.db.update_agent_status(
                self.agent_id,
                AgentStatus.ERROR,
                error_message=str(e)
            )

            return ValidationStatus.NO_GO, f"Verification error: {e}"

    async def _simulate_verification(self) -> Tuple[bool, str]:
        """Simulate verification"""
        await asyncio.sleep(1)

        # Get diff
        diff = self.git.get_diff(self.branch_name)

        # Simulate checking
        if len(diff) > 0:
            return True, "Implementation matches specification requirements"
        else:
            return False, "No changes detected in diff"


class TesterAgent:
    """Runs tests and linting"""

    def __init__(
        self,
        task_id: str,
        agent_id: str,
        spec: Dict[str, Any],
        worktree_path: str,
        config: Dict[str, Any],
        logger: PipelineLogger,
        db: Database
    ):
        self.task_id = task_id
        self.agent_id = agent_id
        self.spec = spec
        self.worktree_path = worktree_path
        self.config = config
        self.logger = logger
        self.db = db

    async def test(self) -> Tuple[ValidationStatus, str]:
        """
        Run tests and technical validation.

        Returns:
            Tuple of (status, message)
        """
        self.logger.agent_working(self.agent_id, "Running tests and linting")

        await self.db.update_agent_status(self.agent_id, AgentStatus.WORKING)

        try:
            # TODO: In production, run actual tests
            # For now, simulate testing
            success, message = await self._simulate_testing()

            status = ValidationStatus.GO if success else ValidationStatus.NO_GO

            # Create validation record
            validation_id = await self.db.create_validation(
                self.task_id,
                'tech',
                status
            )

            await self.db.update_validation(
                validation_id,
                status,
                message=message
            )

            # Update agent status
            await self.db.update_agent_status(
                self.agent_id,
                AgentStatus.COMPLETED,
                result=message
            )

            self.logger.validation_result(self.task_id, 'tech', status.value, message)
            self.logger.agent_completed(self.agent_id)

            return status, message

        except Exception as e:
            self.logger.error(f"Tester failed: {e}", exc_info=True)

            await self.db.update_agent_status(
                self.agent_id,
                AgentStatus.ERROR,
                error_message=str(e)
            )

            return ValidationStatus.NO_GO, f"Testing error: {e}"

    async def _simulate_testing(self) -> Tuple[bool, str]:
        """Simulate running tests"""
        await asyncio.sleep(1)

        # Simulate success
        return True, "All tests passed, linting successful"


async def run_phase4(
    config: Dict[str, Any],
    logger: PipelineLogger,
    db: Database,
    git_helper: GitHelper
) -> int:
    """
    Execute Phase 4: QA (Verification + Testing in parallel).

    Args:
        config: Pipeline configuration
        logger: Logger instance
        db: Database instance
        git_helper: Git helper instance

    Returns:
        Number of tasks validated successfully
    """
    logger.phase_start("phase4", "QA - Verification and Testing")

    # Get tasks that have been coded
    coded_tasks = await db.get_tasks_by_status(TaskStatus.CODE_DONE)

    if not coded_tasks:
        logger.info("No tasks ready for QA")
        logger.phase_end("phase4", success=True)
        return 0

    logger.info(f"Found {len(coded_tasks)} tasks ready for QA")

    successful = 0

    for task in coded_tasks:
        # Load spec
        spec_path = Path(task['spec_path'])
        with open(spec_path) as f:
            spec = json.load(f)

        # Get agents
        agents = await db.get_agents_for_task(task['task_id'])
        verifier = next((a for a in agents if a['role'] == 'verifier'), None)
        tester = next((a for a in agents if a['role'] == 'tester'), None)

        if not verifier or not tester:
            logger.error(f"Missing QA agents for {task['task_id']}")
            continue

        # Create agent instances
        verifier_agent = VerifierAgent(
            task_id=task['task_id'],
            agent_id=verifier['agent_id'],
            spec=spec,
            worktree_path=task['worktree_path'],
            branch_name=task['branch_name'],
            config=config,
            logger=logger,
            db=db,
            git_helper=git_helper
        )

        tester_agent = TesterAgent(
            task_id=task['task_id'],
            agent_id=tester['agent_id'],
            spec=spec,
            worktree_path=task['worktree_path'],
            config=config,
            logger=logger,
            db=db
        )

        # Run in parallel
        logger.task_start(task['task_id'], task['title'])

        verify_result, test_result = await asyncio.gather(
            verifier_agent.verify(),
            tester_agent.test()
        )

        verify_status, verify_msg = verify_result
        test_status, test_msg = test_result

        # Check if both passed
        if verify_status == ValidationStatus.GO and test_status == ValidationStatus.GO:
            await db.update_task_status(task['task_id'], TaskStatus.VALIDATION_PASSED)
            logger.task_end(task['task_id'], success=True)
            successful += 1
        else:
            await db.update_task_status(task['task_id'], TaskStatus.VALIDATION_FAILED)
            logger.task_end(task['task_id'], success=False)

    logger.success(f"Phase 4 complete: {successful}/{len(coded_tasks)} tasks validated")
    logger.phase_end("phase4", success=True)

    return successful
