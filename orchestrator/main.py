"""
Main Pipeline Orchestrator

This is the entry point for the generative agent pipeline.
It orchestrates all phases:
- Phase 0: Master Analyst + Analysts (domain identification + cahiers des charges generation)
- Phase 0.5: Gemini Enrichment (enhance cahiers with external research)
- Phase 1: Dispatcher (worktree creation)
- Phase 2: Specialist Agents (implementation with cahier context)
- Phase 3: QA Agents (verification + testing)
- Phase 4: Merger Agent (integration with interactive conflict resolution)
"""

import asyncio
import sys
import shutil
from pathlib import Path
from typing import Optional
import yaml
import click

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.db import Database
from orchestrator.utils.git_helper import GitHelper
from orchestrator.utils.logger import setup_logger, PipelineLogger

from orchestrator.phases.phase0_master_analysts import run_phase0
from orchestrator.phases.phase0_5_gemini_enrichment import run_phase0_5
from orchestrator.phases.phase1_dispatcher import run_phase1
from orchestrator.phases.phase2_specialists import run_phase2
from orchestrator.phases.phase3_qa import run_phase3
from orchestrator.phases.phase4_merger import run_phase4


class Pipeline:
    """Main pipeline orchestrator"""

    def __init__(self, config_path: str = "config/pipeline_config.yaml",
                 target_project: Optional[str] = None):
        """
        Initialize pipeline.

        Args:
            config_path: Path to pipeline configuration file
            target_project: Path to the target project to work on (optional)
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.logger = self._setup_logger()
        self.db: Optional[Database] = None
        self.git: Optional[GitHelper] = None

        # Target project path (if not provided, will be set during initialization)
        self.target_project: Optional[Path] = Path(target_project) if target_project else None

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
        # Initialize database (stays in Blueprint directory)
        blueprint_dir = Path(__file__).parent.parent
        db_path = blueprint_dir / self.config['database']['path']
        self.db = Database(str(db_path))
        await self.db.initialize()

        self.logger.success(f"Database initialized: {db_path}")

        # Determine target project
        if not self.target_project:
            # Check if config has a default target project
            default_target = self.config.get('general', {}).get('default_target_project')
            if default_target:
                self.target_project = Path(default_target).expanduser().resolve()
            else:
                # Ask user for target project
                self.logger.error("No target project specified!")
                self.logger.info("Please specify a target project using --project option")
                self.logger.info("Example: python orchestrator/main.py start 'requirement' --project /path/to/project")
                raise ValueError("Target project must be specified")

        # Validate target project
        self.target_project = self.target_project.expanduser().resolve()

        if not self.target_project.exists():
            raise ValueError(f"Target project does not exist: {self.target_project}")

        if not self.target_project.is_dir():
            raise ValueError(f"Target project is not a directory: {self.target_project}")

        # Check if it's a git repository
        git_dir = self.target_project / ".git"
        if not git_dir.exists():
            raise ValueError(f"Target project is not a git repository: {self.target_project}")

        # Initialize git helper for TARGET PROJECT
        self.git = GitHelper(str(self.target_project))

        self.logger.success(f"Git helper initialized for target project: {self.target_project}")

    async def cleanup(self, phase_failed: Optional[str] = None, exception: Optional[Exception] = None):
        """
        Cleanup resources with phase-aware logic.

        Args:
            phase_failed: Name of the phase that failed (e.g., "phase0", "phase1")
            exception: The exception that caused the failure
        """
        # Phase-aware cleanup
        if phase_failed:
            self.logger.warning(f"Cleaning up after {phase_failed} failure...")

            if phase_failed in ["phase0", "phase0.5", "phase1"]:
                # No real code exists yet - clean everything
                await self._cleanup_all_temp_files()
                self.logger.info("Cleaned up all temporary planning files (no code was generated)")

            elif phase_failed in ["phase2", "phase3", "phase4"]:
                # Real code exists in worktrees - keep code, clean planning docs
                await self._cleanup_cahiers_only()
                self.logger.info("Cleaned up planning documents (kept code changes)")

        # Always close database connection
        if self.db:
            await self.db.close()
            self.logger.info("Database connection closed")

    async def _cleanup_all_temp_files(self):
        """
        Clean up all temporary files when no real code exists.
        Used when Phase 0, 0.5, or 1 fails.
        """
        try:
            # Clean cahiers_charges directory (in Blueprint)
            blueprint_dir = Path(__file__).parent.parent
            cahiers_dir = blueprint_dir / self.config.get('phase0', {}).get('cahiers_charges_dir', 'cahiers_charges')
            if cahiers_dir.exists() and cahiers_dir.is_dir():
                # Keep the README.md if it exists
                readme_file = cahiers_dir / "README.md"
                readme_content = None
                if readme_file.exists():
                    readme_content = readme_file.read_text()

                # Remove all subdirectories and files except README
                for item in cahiers_dir.iterdir():
                    if item.name != "README.md":
                        if item.is_dir():
                            shutil.rmtree(item)
                            self.logger.debug(f"Removed directory: {item}")
                        else:
                            item.unlink()
                            self.logger.debug(f"Removed file: {item}")

                # Reset index.json to empty state
                index_file = cahiers_dir / "index.json"
                index_file.write_text('{"version": "1.0", "description": "Index des cahiers des charges générés par les agents analystes", "domains": {}, "last_updated": null}')

                self.logger.info(f"Cleaned up cahiers directory: {cahiers_dir}")

            # Clean worktrees if they exist and are empty (in target project)
            if self.target_project:
                worktrees_dir = self.target_project / self.config.get('git', {}).get('worktrees_dir', '.worktrees')
                if worktrees_dir.exists() and worktrees_dir.is_dir():
                    for worktree in worktrees_dir.iterdir():
                        if worktree.is_dir():
                            # Check if worktree is empty (no commits)
                            if self._is_worktree_empty(worktree):
                                shutil.rmtree(worktree)
                                self.logger.debug(f"Removed empty worktree: {worktree}")

            # Clean database entries for tasks that haven't generated code
            if self.db:
                # Delete tasks with status CAHIER_READY or DISPATCHED (no code yet)
                await self.db.delete_tasks_by_status(['cahier_ready', 'dispatched'])
                self.logger.info("Cleaned up database entries for uncommitted tasks")

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

    async def _cleanup_cahiers_only(self):
        """
        Clean up only planning documents, keep code changes.
        Used when Phase 2+ fails but code has been generated.
        """
        try:
            # Only clean cahiers (in Blueprint), keep worktrees with code
            blueprint_dir = Path(__file__).parent.parent
            cahiers_dir = blueprint_dir / self.config.get('phase0', {}).get('cahiers_charges_dir', 'cahiers_charges')
            if cahiers_dir.exists() and cahiers_dir.is_dir():
                # Remove all content except README
                for item in cahiers_dir.iterdir():
                    if item.name != "README.md":
                        if item.is_dir():
                            shutil.rmtree(item)
                        else:
                            item.unlink()

                # Reset index.json
                index_file = cahiers_dir / "index.json"
                index_file.write_text('{"version": "1.0", "description": "Index des cahiers des charges générés par les agents analystes", "domains": {}, "last_updated": null}')

                self.logger.info("Cleaned up cahiers (kept code in worktrees)")

            # Mark tasks as FAILED in database but don't delete them
            if self.db:
                await self.db.mark_incomplete_tasks_as_failed()
                self.logger.info("Marked incomplete tasks as FAILED in database")

        except Exception as e:
            self.logger.error(f"Error during cahiers cleanup: {e}")

    def _is_worktree_empty(self, worktree_path: Path) -> bool:
        """
        Check if a worktree has any commits (i.e., real code changes).

        Args:
            worktree_path: Path to the worktree directory

        Returns:
            True if worktree has no commits, False otherwise
        """
        try:
            # Check if there are any files other than .git
            non_git_files = [f for f in worktree_path.iterdir() if f.name != '.git']
            return len(non_git_files) == 0
        except Exception:
            return True  # If we can't check, assume it's empty

    def _get_failed_phase(self) -> Optional[str]:
        """
        Determine which phase failed based on the current pipeline state.

        Returns:
            Name of the failed phase or None
        """
        # This is tracked during pipeline execution
        return getattr(self, '_current_phase', None)

    async def run_full_pipeline(self, requirement: str):
        """
        Run the complete pipeline from requirement to merged code.

        Args:
            requirement: High-level business requirement
        """
        self.logger.header("GENERATIVE AGENT PIPELINE")
        self.logger.info(f"Requirement: {requirement}")
        self.logger.separator()

        self._current_phase = None  # Track current phase for cleanup

        try:
            # Initialize
            await self.initialize()

            # Phase 0: Master Analyst + Analysts (generates cahiers + tasks)
            if self.config['phase0'].get('enabled', True):
                self._current_phase = "phase0"
                cahiers_count = await run_phase0(requirement, self.config, self.logger, self.db)
                self.logger.info(f"Phase 0: Generated {cahiers_count} cahiers des charges")
            else:
                self.logger.warning("Phase 0 disabled, skipping")
                return

            # Phase 0.5: Gemini Enrichment (enhance cahiers with research)
            if self.config.get('phase0_5', {}).get('enabled', False):
                self._current_phase = "phase0.5"
                enriched_count = await run_phase0_5(self.config, self.logger, self.db)
                self.logger.info(f"Phase 0.5: Enriched {enriched_count} cahiers des charges")
            else:
                self.logger.info("Phase 0.5 disabled, skipping enrichment")

            # Phase 1: Dispatcher (creates worktrees)
            if self.config['phase1'].get('enabled', True):
                self._current_phase = "phase1"
                dispatched_count = await run_phase1(self.config, self.logger, self.db, self.git)
                self.logger.info(f"Phase 1: Dispatched {dispatched_count} tasks")
            else:
                self.logger.warning("Phase 1 disabled, skipping")
                return

            # Phase 2: Specialists (implementation with cahier context)
            if self.config['phase2'].get('enabled', True):
                self._current_phase = "phase2"
                implemented_count = await run_phase2(self.config, self.logger, self.db, self.git)
                self.logger.info(f"Phase 2: Implemented {implemented_count} tasks")
            else:
                self.logger.warning("Phase 2 disabled, skipping")
                return

            # Phase 3: QA (verification + testing)
            if self.config['phase3'].get('enabled', True):
                self._current_phase = "phase3"
                validated_count = await run_phase3(self.config, self.logger, self.db, self.git)
                self.logger.info(f"Phase 3: Validated {validated_count} tasks")
            else:
                self.logger.warning("Phase 3 disabled, skipping")
                return

            # Phase 4: Merger (integration with conflict resolution)
            if self.config['phase4'].get('enabled', True):
                self._current_phase = "phase4"
                merged_count = await run_phase4(self.config, self.logger, self.db, self.git)
                self.logger.info(f"Phase 4: Merged {merged_count} tasks")
            else:
                self.logger.warning("Phase 4 disabled, skipping")
                return

            # Display final stats
            await self.display_stats()

            self.logger.header("PIPELINE COMPLETE")
            self._current_phase = None  # Reset after successful completion

        except Exception as e:
            self.logger.error(f"Pipeline failed in {self._current_phase}: {e}", exc_info=True)
            # Cleanup with phase-aware logic
            await self.cleanup(phase_failed=self._current_phase, exception=e)
            raise

        finally:
            # Final cleanup if not already done
            if self._current_phase is None:
                await self.cleanup()

    async def run_phase(self, phase: str, **kwargs):
        """
        Run a specific phase only.

        Args:
            phase: Phase number (0, 0.5, 1, 2, 3, 4)
            **kwargs: Phase-specific arguments
        """
        await self.initialize()

        try:
            if phase == "0":
                requirement = kwargs.get('requirement')
                if not requirement:
                    raise ValueError("Phase 0 requires 'requirement' argument")
                cahiers_count = await run_phase0(requirement, self.config, self.logger, self.db)
                self.logger.info(f"Phase 0 complete: {cahiers_count} cahiers generated")

            elif phase == "0.5":
                enriched_count = await run_phase0_5(self.config, self.logger, self.db)
                self.logger.info(f"Phase 0.5 complete: {enriched_count} cahiers enriched")

            elif phase == "1":
                dispatched_count = await run_phase1(self.config, self.logger, self.db, self.git)
                self.logger.info(f"Phase 1 complete: {dispatched_count} tasks dispatched")

            elif phase == "2":
                implemented_count = await run_phase2(self.config, self.logger, self.db, self.git)
                self.logger.info(f"Phase 2 complete: {implemented_count} tasks implemented")

            elif phase == "3":
                validated_count = await run_phase3(self.config, self.logger, self.db, self.git)
                self.logger.info(f"Phase 3 complete: {validated_count} tasks validated")

            elif phase == "4":
                merged_count = await run_phase4(self.config, self.logger, self.db, self.git)
                self.logger.info(f"Phase 4 complete: {merged_count} tasks merged")

            else:
                raise ValueError(f"Invalid phase: {phase}. Valid phases are 0, 0.5, 1, 2, 3, 4")

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
@click.option('--project', type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
              help='Target project path to work on')
@click.option('--config', default='config/pipeline_config.yaml', help='Configuration file')
def start(requirement: str, project: Optional[str], config: str):
    """
    Start the full pipeline with a business requirement.

    Example:
        python main.py start "Build a user authentication system" --project /path/to/my-app
    """
    pipeline = Pipeline(config, target_project=project)
    asyncio.run(pipeline.run_full_pipeline(requirement))


@cli.command()
@click.option('--project', type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
              help='Target project path to work on')
@click.option('--config', default='config/pipeline_config.yaml', help='Configuration file')
def init(project: Optional[str], config: str):
    """
    Initialize the pipeline (create database, check git).

    Example:
        python main.py init --project /path/to/my-app
    """
    pipeline = Pipeline(config, target_project=project)

    async def _init():
        await pipeline.initialize()
        pipeline.logger.success("Pipeline initialized successfully")
        await pipeline.cleanup()

    asyncio.run(_init())


@cli.command()
@click.option('--project', type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
              help='Target project path to work on')
@click.option('--config', default='config/pipeline_config.yaml', help='Configuration file')
def status(project: Optional[str], config: str):
    """
    Display pipeline status and statistics.

    Example:
        python main.py status --project /path/to/my-app
    """
    pipeline = Pipeline(config, target_project=project)

    async def _status():
        await pipeline.initialize()
        await pipeline.display_stats()
        await pipeline.cleanup()

    asyncio.run(_status())


@cli.command()
@click.argument('phase', type=click.Choice(['0', '0.5', '1', '2', '3', '4']))
@click.option('--project', type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
              help='Target project path to work on')
@click.option('--requirement', help='Business requirement (Phase 0 only)')
@click.option('--config', default='config/pipeline_config.yaml', help='Configuration file')
def run_phase(phase: str, project: Optional[str], requirement: Optional[str], config: str):
    """
    Run a specific phase of the pipeline.

    Phases:
      0   - Master Analyst + Analysts (generate cahiers des charges)
      0.5 - Gemini Enrichment (enhance cahiers with research)
      1   - Dispatcher (create worktrees)
      2   - Specialists (implementation with cahier context)
      3   - QA (verification + testing)
      4   - Merger (integration with conflict resolution)

    Example:
        python main.py run-phase 0 --project /path/to/my-app --requirement "Improve application security"
        python main.py run-phase 0.5 --project /path/to/my-app
        python main.py run-phase 1 --project /path/to/my-app
    """
    pipeline = Pipeline(config, target_project=project)
    asyncio.run(pipeline.run_phase(phase, requirement=requirement))


@cli.command()
@click.option('--project', type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
              help='Target project path to work on')
@click.option('--config', default='config/pipeline_config.yaml', help='Configuration file')
@click.option('--force', is_flag=True, help='Force cleanup even if code exists')
@click.option('--dry-run', is_flag=True, help='Show what would be cleaned without actually doing it')
def cleanup(project: Optional[str], config: str, force: bool, dry_run: bool):
    """
    Clean up failed tasks and orphaned resources.

    Removes:
    - Cahiers des charges for failed/incomplete tasks
    - Empty worktrees (no commits)
    - Database entries for failed tasks (with --force)

    Examples:
        python main.py cleanup --project /path/to/my-app              # Clean orphaned resources
        python main.py cleanup --project /path/to/my-app --dry-run    # Preview what would be cleaned
        python main.py cleanup --project /path/to/my-app --force      # Force cleanup including code
    """
    pipeline = Pipeline(config, target_project=project)

    async def _cleanup():
        await pipeline.initialize()

        pipeline.logger.header("CLEANUP - Orphaned Resources")

        if dry_run:
            pipeline.logger.warning("DRY RUN MODE - No changes will be made")

        # Count resources to clean
        blueprint_dir = Path(__file__).parent.parent
        cahiers_dir = blueprint_dir / pipeline.config.get('phase0', {}).get('cahiers_charges_dir', 'cahiers_charges')
        worktrees_dir = pipeline.target_project / pipeline.config.get('git', {}).get('worktrees_dir', '.worktrees') if pipeline.target_project else None

        cahier_domains = []
        empty_worktrees = []

        # Check cahiers
        if cahiers_dir.exists():
            cahier_domains = [d for d in cahiers_dir.iterdir()
                            if d.is_dir() and d.name not in ['README.md']]

        # Check worktrees
        if worktrees_dir and worktrees_dir.exists():
            for worktree in worktrees_dir.iterdir():
                if worktree.is_dir():
                    if pipeline._is_worktree_empty(worktree) or force:
                        empty_worktrees.append(worktree)

        # Report what will be cleaned
        pipeline.logger.info(f"Found {len(cahier_domains)} cahier domains to clean")
        pipeline.logger.info(f"Found {len(empty_worktrees)} worktrees to clean")

        if not cahier_domains and not empty_worktrees:
            pipeline.logger.success("No orphaned resources found!")
            await pipeline.cleanup()
            return

        # Ask for confirmation if not dry run and not force mode
        if not dry_run and not force:
            if not pipeline.logger.confirm("Proceed with cleanup?", default=True):
                pipeline.logger.info("Cleanup cancelled")
                await pipeline.cleanup()
                return

        # Perform cleanup (only if not dry run)
        if not dry_run:
            if force:
                pipeline.logger.warning("FORCE MODE - Cleaning everything including code")
                await pipeline._cleanup_all_temp_files()
            else:
                await pipeline._cleanup_cahiers_only()

                # Clean empty worktrees
                for worktree in empty_worktrees:
                    shutil.rmtree(worktree)
                    pipeline.logger.info(f"Removed empty worktree: {worktree.name}")

            pipeline.logger.success("Cleanup complete!")

        await pipeline.cleanup()

    asyncio.run(_cleanup())


@cli.command()
@click.option('--config', default='config/pipeline_config.yaml', help='Configuration file')
def reset(config: str):
    """
    Reset the pipeline (delete database).

    Example:
        python main.py reset
    """
    pipeline = Pipeline(config)

    # Database is always in Blueprint directory, not in target project
    blueprint_dir = Path(__file__).parent.parent
    db_path = blueprint_dir / pipeline.config['database']['path']

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
