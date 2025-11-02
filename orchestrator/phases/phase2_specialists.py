"""
Phase 2: Specialist Agents

Specialist agents work in parallel, each in their dedicated worktree,
implementing the requirements specified in their cahier des charges.

Key difference from old Phase 3 (Coder):
- Loads and injects the cahier des charges (Markdown) into the prompt
- Provides richer context for implementation
"""

import asyncio
import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path

from orchestrator.db import Database, TaskStatus, AgentStatus
from orchestrator.utils.git_helper import GitHelper
from orchestrator.utils.logger import PipelineLogger
from orchestrator.agent_factory import AgentFactory


class SpecialistAgent:
    """A specialist agent that implements a task with cahier des charges context"""

    def __init__(
        self,
        task_id: str,
        agent_id: str,
        spec_path: str,
        worktree_path: str,
        branch_name: str,
        config: Dict[str, Any],
        logger: PipelineLogger,
        db: Database,
        git_helper: GitHelper,
        agent_factory: AgentFactory
    ):
        """
        Initialize specialist agent.

        Args:
            task_id: Task ID
            agent_id: Agent ID
            spec_path: Path to spec file (cahier markdown)
            worktree_path: Path to git worktree
            branch_name: Git branch name
            config: Pipeline configuration
            logger: Logger instance
            db: Database instance
            git_helper: Git helper
            agent_factory: Agent factory for prompt generation
        """
        self.task_id = task_id
        self.agent_id = agent_id
        self.spec_path = spec_path
        self.worktree_path = worktree_path
        self.branch_name = branch_name
        self.config = config
        self.logger = logger
        self.db = db
        self.git = git_helper
        self.factory = agent_factory

        self.phase2_config = config.get('phase2', {})

    async def implement(self) -> bool:
        """
        Implement the task using the cahier des charges.

        Returns:
            True if implementation successful, False otherwise
        """
        self.logger.info(f"[{self.agent_id}] Starting implementation for {self.task_id}")

        # Update agent status
        await self.db.update_agent_status(self.agent_id, AgentStatus.WORKING)

        # Update task status
        await self.db.update_task_status(self.task_id, TaskStatus.SPECIALIST_WORKING)

        try:
            # Step 1: Load the cahier des charges
            cahier_content = await self._load_cahier()

            if not cahier_content:
                self.logger.error(f"[{self.agent_id}] Failed to load cahier")
                return False

            self.logger.info(f"[{self.agent_id}] Loaded cahier ({len(cahier_content)} chars)")

            # Step 2: Get template
            template_name = self.phase2_config.get('specialist_template', 'senior-engineer')

            # Step 3: Create prompt with cahier injected
            prompt = await self._create_specialist_prompt(
                cahier_content,
                template_name
            )

            self.logger.debug(f"[{self.agent_id}] Generated prompt ({len(prompt)} chars)")

            # Step 4: Simulate implementation
            # TODO: Replace with actual AI model call
            implementation_result = await self._simulate_implementation()

            # Step 5: Commit and push
            await self._commit_and_push(implementation_result)

            # Mark as completed
            await self.db.update_agent_status(
                self.agent_id,
                AgentStatus.COMPLETED,
                result=f"Implementation completed in {self.worktree_path}"
            )

            await self.db.update_task_status(self.task_id, TaskStatus.CODE_DONE)

            self.logger.success(f"[{self.agent_id}] Implementation complete")

            return True

        except Exception as e:
            self.logger.error(f"[{self.agent_id}] Implementation failed: {e}")
            await self.db.update_agent_status(
                self.agent_id,
                AgentStatus.ERROR,
                error_message=str(e)
            )
            return False

    async def _load_cahier(self) -> Optional[str]:
        """
        Load the cahier des charges for this task.

        Returns:
            Cahier content in Markdown, or None if failed
        """
        # Try to get cahier from database
        cahier = await self.db.get_cahier_for_task(self.task_id)

        if cahier:
            # Load from DB-stored path
            content = await self.db.load_cahier_content(cahier['cahier_id'])
            if content:
                return content

        # Fallback: Try to load from spec_path directly
        try:
            spec_file = Path(self.spec_path)
            if spec_file.exists():
                with open(spec_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Check if it's markdown
                    if content.startswith('#') or '##' in content:
                        return content
        except Exception as e:
            self.logger.warning(f"[{self.agent_id}] Could not load from spec_path: {e}")

        return None

    async def _create_specialist_prompt(
        self,
        cahier_content: str,
        template_name: str
    ) -> str:
        """
        Create the specialist agent prompt with cahier injection.

        Args:
            cahier_content: Cahier des charges content in Markdown
            template_name: Template to use

        Returns:
            Complete prompt for the specialist agent
        """
        # Create basic context
        context = {
            'task_id': self.task_id,
            'worktree_path': self.worktree_path,
            'branch_name': self.branch_name
        }

        # Get base prompt from template
        base_prompt = self.factory.create_agent_prompt(
            template_name=template_name,
            context=context,
            role_specialization="Implement the requirements specified in the cahier des charges"
        )

        # Inject cahier content
        full_prompt = f"""{base_prompt}

---

## CAHIER DES CHARGES (Specification Document)

The following cahier des charges has been created by an analyst agent to guide your implementation.
Follow its recommendations for architecture, technologies, and best practices.

{cahier_content}

---

## YOUR TASK

1. Carefully read the cahier des charges above
2. Implement the features and requirements specified
3. Follow the recommended architecture and file structure
4. Use the technologies and libraries mentioned
5. Ensure all acceptance criteria can be met
6. Write clean, maintainable code
7. Add appropriate tests

## IMPORTANT REMINDERS

- Work exclusively in: {self.worktree_path}
- Commit to branch: {self.branch_name}
- Follow the cahier's technical specifications precisely
- If the cahier mentions security considerations, implement them
- Document any deviations from the cahier (if necessary)

Begin implementation now.
"""

        return full_prompt

    async def _simulate_implementation(self) -> str:
        """
        Simulate code implementation (placeholder for AI call).

        In production, this would call an AI model with the specialist prompt.

        Returns:
            Simulated implementation result
        """
        # Simulate work delay
        await asyncio.sleep(2)

        result = f"""Simulated implementation for {self.task_id}:

- Created files in {self.worktree_path}
- Followed cahier des charges specifications
- Implemented core functionality
- Added tests

Ready for validation.
"""
        return result

    async def _commit_and_push(self, implementation_result: str):
        """
        Commit changes and push to remote.

        Args:
            implementation_result: Description of what was implemented
        """
        # Format commit message
        commit_message = f"""Implement {self.task_id}

{implementation_result}

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
"""

        self.logger.info(f"[{self.agent_id}] Committing changes...")

        # TODO: In production, actually commit and push
        # For now, simulate
        await asyncio.sleep(0.5)

        self.logger.success(f"[{self.agent_id}] Changes committed and pushed to {self.branch_name}")


async def run_phase2(
    config: Dict[str, Any],
    logger: PipelineLogger,
    db: Database,
    git_helper: GitHelper
) -> int:
    """
    Execute Phase 2: Specialist Agents.

    Args:
        config: Pipeline configuration
        logger: Logger instance
        db: Database instance
        git_helper: Git helper instance

    Returns:
        Number of tasks implemented
    """
    if not config.get('phase2', {}).get('enabled', True):
        logger.warning("Phase 2 is disabled in configuration")
        return 0

    logger.phase_start("phase2", "Specialist Agents - Implementation")

    # Get tasks ready for specialists (DISPATCHED status)
    tasks = await db.get_tasks_by_status(TaskStatus.DISPATCHED)

    if not tasks:
        logger.info("No tasks ready for implementation")
        logger.phase_end("phase2", success=True)
        return 0

    logger.info(f"Found {len(tasks)} tasks ready for implementation")

    # Create agent factory
    factory = AgentFactory(config['agents']['templates_path'])

    # Parallel execution with semaphore
    max_parallel = config.get('phase2', {}).get('max_parallel_specialists', 3)
    semaphore = asyncio.Semaphore(max_parallel)

    async def run_specialist(task: Dict[str, Any]):
        async with semaphore:
            agent_id = f"Specialist-{task['task_id']}"

            # Create specialist agent instance
            specialist = SpecialistAgent(
                task_id=task['task_id'],
                agent_id=agent_id,
                spec_path=task['spec_path'],
                worktree_path=task['worktree_path'],
                branch_name=task['branch_name'],
                config=config,
                logger=logger,
                db=db,
                git_helper=git_helper,
                agent_factory=factory
            )

            # Load spec to get access config
            import json
            spec = {}
            if task.get('spec_path') and os.path.exists(task['spec_path']):
                with open(task['spec_path'], 'r') as f:
                    spec = json.load(f)

            # Get template name
            specialist_template = config.get('phase2', {}).get('specialist_template', 'senior-engineer')

            # Get merged access control config (template + spec + defaults)
            merged_access = factory.get_merged_access_config(
                template_name=specialist_template,
                spec=spec
            )

            # Get access mode from config
            access_mode = config.get('security', {}).get('access_control', {}).get('mode', 'block')

            # Create agent in DB with access control
            await db.create_agent(
                agent_id=agent_id,
                task_id=task['task_id'],
                role='specialist',
                template_name=specialist_template,
                allow_paths=merged_access.get('allow'),
                exclude_paths=merged_access.get('exclude'),
                access_mode=access_mode,
                worktree_path=task.get('worktree_path')
            )

            # Run implementation
            success = await specialist.implement()

            return success

    # Run all specialists in parallel
    results = await asyncio.gather(
        *[run_specialist(task) for task in tasks],
        return_exceptions=True
    )

    # Count successes
    successful_count = sum(1 for r in results if r is True)
    failed_count = len(results) - successful_count

    logger.success(f"Phase 2 complete: {successful_count} successful, {failed_count} failed")
    logger.phase_end("phase2", success=True)

    return successful_count
