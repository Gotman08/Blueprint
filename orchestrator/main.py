"""
Main Pipeline Orchestrator

This is the entry point for the generative agent pipeline.
It orchestrates all 5 phases:
- Phase 0: Master Analyst (domain identification)
- Phase 1: Specialist Analysts (specification generation)
- Phase 2: Dispatcher (worktree + team creation)
- Phase 3: Coder Agents (implementation)
- Phase 4: QA Agents (verification + testing)
- Phase 5: Merger Agent (integration with validation)
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional
import yaml
import click

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.db import Database
from orchestrator.utils.git_helper import GitHelper
from orchestrator.utils.logger import setup_logger, PipelineLogger

from orchestrator.phases.phase0_master import run_phase0
from orchestrator.phases.phase1_specialists import run_phase1
from orchestrator.phases.phase2_dispatcher import run_phase2
from orchestrator.phases.phase3_coder import run_phase3
from orchestrator.phases.phase4_qa import run_phase4
from orchestrator.phases.phase5_merger import run_phase5


class Pipeline:
    """Main pipeline orchestrator"""

    def __init__(self, config_path: str = "config/pipeline_config.yaml"):
        """
        Initialize pipeline.

        Args:
            config_path: Path to pipeline configuration file
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.logger = self._setup_logger()
        self.db: Optional[Database] = None
        self.git: Optional[GitHelper] = None

    def _load_config(self) -> dict:
        """Load pipeline configuration"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path) as f:
            return yaml.safe_load(f)

    def _setup_logger(self) -> PipelineLogger:
        """Setup pipeline logger"""
        general_config = self.config.get('general', {})

        log_level = general_config.get('log_level', 'INFO')
        log_file = general_config.get('log_file')

        # Create logs directory if needed
        if log_file:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)

        return setup_logger(log_level=log_level, log_file=log_file)

    async def initialize(self):
        """Initialize database and git helper"""
        # Initialize database
        db_path = self.config['database']['path']
        self.db = Database(db_path)
        await self.db.initialize()

        self.logger.success(f"Database initialized: {db_path}")

        # Initialize git helper
        repo_path = Path.cwd()
        self.git = GitHelper(str(repo_path))

        self.logger.success(f"Git helper initialized for: {repo_path}")

    async def cleanup(self):
        """Cleanup resources"""
        if self.db:
            await self.db.close()
            self.logger.info("Database connection closed")

    async def run_full_pipeline(self, requirement: str):
        """
        Run the complete pipeline from requirement to merged code.

        Args:
            requirement: High-level business requirement
        """
        self.logger.header("GENERATIVE AGENT PIPELINE")
        self.logger.info(f"Requirement: {requirement}")
        self.logger.separator()

        try:
            # Initialize
            await self.initialize()

            # Phase 0: Master Analyst
            if self.config['phase0'].get('enabled', True):
                domains = await run_phase0(requirement, self.config, self.logger)
                self.logger.info(f"Identified {len(domains)} domains")
            else:
                self.logger.warning("Phase 0 disabled, skipping")
                return

            # Phase 1: Specialist Analysts
            if self.config['phase1'].get('enabled', True):
                specs_count = await run_phase1(domains, self.config, self.logger, self.db)
                self.logger.info(f"Created {specs_count} specifications")
            else:
                self.logger.warning("Phase 1 disabled, skipping")
                return

            # Phase 2: Dispatcher
            if self.config['phase2'].get('enabled', True):
                dispatched = await run_phase2(self.config, self.logger, self.db, self.git)
                self.logger.info(f"Dispatched {dispatched} tasks")
            else:
                self.logger.warning("Phase 2 disabled, skipping")
                return

            # Phase 3: Coder Agents
            if self.config['phase3'].get('enabled', True):
                coded = await run_phase3(self.config, self.logger, self.db, self.git)
                self.logger.info(f"Coded {coded} tasks")
            else:
                self.logger.warning("Phase 3 disabled, skipping")
                return

            # Phase 4: QA Agents
            if self.config['phase4'].get('enabled', True):
                validated = await run_phase4(self.config, self.logger, self.db, self.git)
                self.logger.info(f"Validated {validated} tasks")
            else:
                self.logger.warning("Phase 4 disabled, skipping")
                return

            # Phase 5: Merger Agent
            if self.config['phase5'].get('enabled', True):
                merged = await run_phase5(self.config, self.logger, self.db, self.git)
                self.logger.info(f"Merged {merged} tasks")
            else:
                self.logger.warning("Phase 5 disabled, skipping")
                return

            # Display final stats
            await self.display_stats()

            self.logger.header("PIPELINE COMPLETE")

        except Exception as e:
            self.logger.error(f"Pipeline failed: {e}", exc_info=True)
            raise

        finally:
            await self.cleanup()

    async def run_phase(self, phase: str, **kwargs):
        """
        Run a specific phase only.

        Args:
            phase: Phase number (0-5)
            **kwargs: Phase-specific arguments
        """
        await self.initialize()

        try:
            if phase == "0":
                requirement = kwargs.get('requirement')
                if not requirement:
                    raise ValueError("Phase 0 requires 'requirement' argument")
                await run_phase0(requirement, self.config, self.logger)

            elif phase == "1":
                from orchestrator.phases.phase0_master import Domain
                # This would need domains from Phase 0
                self.logger.error("Phase 1 requires domains from Phase 0")

            elif phase == "2":
                await run_phase2(self.config, self.logger, self.db, self.git)

            elif phase == "3":
                await run_phase3(self.config, self.logger, self.db, self.git)

            elif phase == "4":
                await run_phase4(self.config, self.logger, self.db, self.git)

            elif phase == "5":
                await run_phase5(self.config, self.logger, self.db, self.git)

            else:
                raise ValueError(f"Invalid phase: {phase}")

        finally:
            await self.cleanup()

    async def display_stats(self):
        """Display pipeline statistics"""
        stats = await self.db.get_stats()
        self.logger.stats(stats)


# CLI Interface

@click.group()
def cli():
    """Generative Agent Pipeline - Automated development workflow"""
    pass


@cli.command()
@click.argument('requirement')
@click.option('--config', default='config/pipeline_config.yaml', help='Configuration file')
def start(requirement: str, config: str):
    """
    Start the full pipeline with a business requirement.

    Example:
        python main.py start "Build a user authentication system"
    """
    pipeline = Pipeline(config)
    asyncio.run(pipeline.run_full_pipeline(requirement))


@cli.command()
@click.option('--config', default='config/pipeline_config.yaml', help='Configuration file')
def init(config: str):
    """
    Initialize the pipeline (create database, check git).

    Example:
        python main.py init
    """
    pipeline = Pipeline(config)

    async def _init():
        await pipeline.initialize()
        pipeline.logger.success("Pipeline initialized successfully")
        await pipeline.cleanup()

    asyncio.run(_init())


@cli.command()
@click.option('--config', default='config/pipeline_config.yaml', help='Configuration file')
def status(config: str):
    """
    Display pipeline status and statistics.

    Example:
        python main.py status
    """
    pipeline = Pipeline(config)

    async def _status():
        await pipeline.initialize()
        await pipeline.display_stats()
        await pipeline.cleanup()

    asyncio.run(_status())


@cli.command()
@click.argument('phase', type=click.Choice(['0', '1', '2', '3', '4', '5']))
@click.option('--requirement', help='Business requirement (Phase 0 only)')
@click.option('--config', default='config/pipeline_config.yaml', help='Configuration file')
def run_phase(phase: str, requirement: Optional[str], config: str):
    """
    Run a specific phase of the pipeline.

    Example:
        python main.py run-phase 2
    """
    pipeline = Pipeline(config)
    asyncio.run(pipeline.run_phase(phase, requirement=requirement))


@cli.command()
@click.option('--config', default='config/pipeline_config.yaml', help='Configuration file')
def reset(config: str):
    """
    Reset the pipeline (delete database).

    Example:
        python main.py reset
    """
    pipeline = Pipeline(config)

    db_path = Path(pipeline.config['database']['path'])

    if db_path.exists():
        if pipeline.logger.confirm(f"Delete database {db_path}?", default=False):
            db_path.unlink()
            pipeline.logger.success("Database deleted")
        else:
            pipeline.logger.info("Reset cancelled")
    else:
        pipeline.logger.info("Database does not exist")


if __name__ == '__main__':
    cli()
