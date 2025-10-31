"""
Logger - Centralized logging system for the pipeline.

Provides structured logging with colors, phases tracking, and file output.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text


class PipelineLogger:
    """Structured logger for the generative agent pipeline"""

    # Phase colors
    PHASE_COLORS = {
        'phase0': 'magenta',
        'phase1': 'cyan',
        'phase2': 'yellow',
        'phase3': 'green',
        'phase4': 'blue',
        'phase5': 'red',
        'system': 'white',
        'error': 'red',
        'success': 'green',
        'warning': 'yellow',
        'info': 'blue'
    }

    def __init__(
        self,
        name: str = "pipeline",
        log_level: int = logging.INFO,
        log_file: Optional[str] = None
    ):
        """
        Initialize pipeline logger.

        Args:
            name: Logger name
            log_level: Logging level (default: INFO)
            log_file: Optional log file path
        """
        self.console = Console()
        self.logger = logging.getLogger(name)
        self.logger.setLevel(log_level)

        # Clear existing handlers
        self.logger.handlers.clear()

        # Rich console handler
        console_handler = RichHandler(
            console=self.console,
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            show_time=True,
            show_path=False
        )
        console_handler.setLevel(log_level)
        self.logger.addHandler(console_handler)

        # File handler if specified
        if log_file:
            self._add_file_handler(log_file, log_level)

        self.current_phase: Optional[str] = None

    def _add_file_handler(self, log_file: str, log_level: int):
        """Add file handler for persistent logging"""
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path, mode='a', encoding='utf-8')
        file_handler.setLevel(log_level)

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)

        self.logger.addHandler(file_handler)

    def set_phase(self, phase: str):
        """Set current pipeline phase for context"""
        self.current_phase = phase

    def _format_message(self, message: str, phase: Optional[str] = None) -> str:
        """Add phase prefix to message"""
        active_phase = phase or self.current_phase
        if active_phase:
            return f"[{active_phase.upper()}] {message}"
        return message

    # Core logging methods

    def debug(self, message: str, phase: Optional[str] = None):
        """Log debug message"""
        self.logger.debug(self._format_message(message, phase))

    def info(self, message: str, phase: Optional[str] = None):
        """Log info message"""
        self.logger.info(self._format_message(message, phase))

    def warning(self, message: str, phase: Optional[str] = None):
        """Log warning message"""
        self.logger.warning(self._format_message(message, phase))

    def error(self, message: str, phase: Optional[str] = None, exc_info: bool = False):
        """Log error message"""
        self.logger.error(self._format_message(message, phase), exc_info=exc_info)

    def success(self, message: str, phase: Optional[str] = None):
        """Log success message (info level with green color)"""
        formatted = self._format_message(message, phase)
        self.console.print(f"[green]✓[/green] {formatted}")

    # Rich output methods

    def panel(
        self,
        message: str,
        title: Optional[str] = None,
        color: str = "blue",
        expand: bool = False
    ):
        """Print a panel with message"""
        self.console.print(Panel(message, title=title, border_style=color, expand=expand))

    def phase_start(self, phase: str, description: str):
        """Announce phase start with styled panel"""
        self.set_phase(phase)
        color = self.PHASE_COLORS.get(phase.lower(), 'white')

        self.console.print()
        self.panel(
            f"[bold]{description}[/bold]",
            title=f"Phase {phase[-1]} - {phase.upper()}",
            color=color,
            expand=False
        )
        self.info(f"Started: {description}", phase=phase)

    def phase_end(self, phase: str, success: bool = True):
        """Announce phase end"""
        status = "✓ COMPLETED" if success else "✗ FAILED"
        color = "green" if success else "red"

        self.console.print(f"[{color}]{status}[/{color}] {phase.upper()}")
        self.info(f"Finished with status: {status}", phase=phase)

    def task_start(self, task_id: str, title: str):
        """Log task start"""
        self.console.print(f"\n[bold cyan]→ Task {task_id}:[/bold cyan] {title}")

    def task_end(self, task_id: str, success: bool = True):
        """Log task completion"""
        status = "✓" if success else "✗"
        color = "green" if success else "red"
        self.console.print(f"[{color}]{status} Task {task_id} completed[/{color}]")

    def agent_created(self, agent_id: str, role: str, task_id: str):
        """Log agent creation"""
        self.console.print(
            f"  [dim]└─ Created agent:[/dim] [yellow]{agent_id}[/yellow] "
            f"[dim](role: {role}, task: {task_id})[/dim]"
        )

    def agent_working(self, agent_id: str, action: str):
        """Log agent activity"""
        self.console.print(f"  [dim]└─ Agent {agent_id}:[/dim] {action}")

    def agent_completed(self, agent_id: str, result: str = "success"):
        """Log agent completion"""
        color = "green" if result == "success" else "yellow"
        self.console.print(f"  [dim]└─[/dim] [{color}]✓ Agent {agent_id} finished[/{color}]")

    def validation_result(
        self,
        task_id: str,
        validator_type: str,
        status: str,
        message: Optional[str] = None
    ):
        """Log validation result"""
        if status == "go":
            icon = "✓"
            color = "green"
            status_text = "PASSED"
        else:
            icon = "✗"
            color = "red"
            status_text = "FAILED"

        self.console.print(
            f"  [{color}]{icon} {validator_type.upper()} validation: {status_text}[/{color}]"
        )

        if message:
            self.console.print(f"    [dim]{message}[/dim]")

    def merge_conflict(self, files: list):
        """Log merge conflict details"""
        self.console.print("\n[red]⚠ MERGE CONFLICTS DETECTED[/red]")
        for file in files:
            self.console.print(f"  [red]✗[/red] {file}")

    def stats(self, stats_dict: dict):
        """Display pipeline statistics in a table"""
        from rich.table import Table

        table = Table(title="Pipeline Statistics", show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")

        for key, value in stats_dict.items():
            # Format key
            formatted_key = key.replace('_', ' ').title()
            table.add_row(formatted_key, str(value))

        self.console.print("\n")
        self.console.print(table)
        self.console.print()

    def progress_bar(self, description: str):
        """Create a progress bar context manager"""
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console
        )

    def separator(self, char: str = "─", length: int = 80):
        """Print a separator line"""
        self.console.print(f"[dim]{char * length}[/dim]")

    def header(self, text: str):
        """Print a header"""
        self.console.print(f"\n[bold cyan]{'=' * 80}[/bold cyan]")
        self.console.print(f"[bold cyan]{text.center(80)}[/bold cyan]")
        self.console.print(f"[bold cyan]{'=' * 80}[/bold cyan]\n")

    def prompt(self, question: str, default: Optional[str] = None) -> str:
        """
        Prompt user for input.

        Args:
            question: Question to ask
            default: Default value if user presses enter

        Returns:
            User input
        """
        if default:
            prompt_text = f"{question} [{default}]: "
        else:
            prompt_text = f"{question}: "

        response = self.console.input(f"[yellow]{prompt_text}[/yellow]")

        return response if response else default

    def confirm(self, question: str, default: bool = False) -> bool:
        """
        Ask yes/no question.

        Args:
            question: Question to ask
            default: Default answer if user presses enter

        Returns:
            True for yes, False for no
        """
        default_str = "Y/n" if default else "y/N"
        response = self.console.input(f"[yellow]{question} [{default_str}]: [/yellow]").strip().lower()

        if not response:
            return default

        return response in ['y', 'yes', 'oui']

    def json_output(self, data: dict, title: Optional[str] = None):
        """Pretty print JSON data"""
        from rich.json import JSON

        if title:
            self.console.print(f"\n[bold]{title}[/bold]")

        self.console.print(JSON.from_data(data))


# Global logger instance
_global_logger: Optional[PipelineLogger] = None


def get_logger(
    name: str = "pipeline",
    log_level: int = logging.INFO,
    log_file: Optional[str] = None
) -> PipelineLogger:
    """
    Get or create global logger instance.

    Args:
        name: Logger name
        log_level: Logging level
        log_file: Optional log file path

    Returns:
        PipelineLogger instance
    """
    global _global_logger

    if _global_logger is None:
        _global_logger = PipelineLogger(name, log_level, log_file)

    return _global_logger


def setup_logger(log_level: str = "INFO", log_file: Optional[str] = None) -> PipelineLogger:
    """
    Setup global logger with configuration.

    Args:
        log_level: Log level as string (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path

    Returns:
        Configured PipelineLogger instance
    """
    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }

    level = level_map.get(log_level.upper(), logging.INFO)

    return get_logger(log_level=level, log_file=log_file)
