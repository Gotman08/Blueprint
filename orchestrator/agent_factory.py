"""
Agent Factory - Creates agent instances from templates.

This module reads agent templates from ~/.claude/agents/ (WSL) and creates
specialized agent instances with injected context for specific tasks.
"""

import os
import re
import subprocess
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import yaml
import logging

from orchestrator.utils.access_control import merge_access_configs
from orchestrator.utils.template_downloader import GitHubTemplateDownloader, TemplateNotFoundError
from orchestrator.utils.template_converter import TemplateConverter

logger = logging.getLogger(__name__)


@dataclass
class AgentTemplate:
    """Represents an agent template loaded from ~/.claude/agents/"""
    name: str
    description: str
    model: str
    color: str
    content: str
    file_path: str
    access_control: Optional[Dict[str, List[str]]] = field(default=None)


class AgentFactory:
    """Creates agent instances from templates stored in WSL or GitHub"""

    def __init__(
        self,
        wsl_agents_path: str = "~/.claude/agents",
        enable_github: bool = True,
        github_cache_dir: Optional[Path] = None
    ):
        """
        Initialize the factory.

        Args:
            wsl_agents_path: Path to agents directory in WSL (default: ~/.claude/agents)
            enable_github: Enable GitHub template downloading (default: True)
            github_cache_dir: Directory to cache GitHub templates (default: ./templates/agents)
        """
        self.wsl_agents_path = wsl_agents_path
        self.enable_github = enable_github
        self.github_cache_dir = github_cache_dir or Path("templates/agents")
        self._template_cache: Dict[str, AgentTemplate] = {}

        # Initialize GitHub components if enabled
        if self.enable_github:
            self.github_downloader = GitHubTemplateDownloader()
            self.template_converter = TemplateConverter()
            logger.info("GitHub template support enabled")
        else:
            self.github_downloader = None
            self.template_converter = None

    def _run_wsl_command(self, command: str) -> str:
        """Execute a command in WSL and return output"""
        try:
            result = subprocess.run(
                ["wsl", "bash", "-c", command],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"WSL command failed: {e.stderr}")

    def _read_wsl_file(self, wsl_path: str) -> str:
        """Read a file from WSL filesystem"""
        # Expand ~ to home directory
        expanded_path = wsl_path.replace("~", "$HOME")
        command = f"cat {expanded_path}"
        return self._run_wsl_command(command)

    def _list_wsl_agents(self) -> List[str]:
        """List all agent files in WSL agents directory"""
        expanded_path = self.wsl_agents_path.replace("~", "$HOME")
        command = f"ls {expanded_path}/*.md 2>/dev/null || echo ''"
        output = self._run_wsl_command(command)

        if not output.strip():
            return []

        # Extract just the filenames
        files = output.strip().split('\n')
        return [os.path.basename(f) for f in files if f.endswith('.md')]

    def _parse_agent_template(self, content: str, filename: str) -> AgentTemplate:
        """
        Parse agent markdown file with YAML frontmatter.

        Expected format:
        ---
        name: agent-name
        description: description text
        model: opus
        color: purple
        ---
        # Agent content here
        """
        # Extract YAML frontmatter
        yaml_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.DOTALL)

        if not yaml_match:
            raise ValueError(f"Invalid agent template format in {filename}")

        yaml_content = yaml_match.group(1)
        markdown_content = yaml_match.group(2)

        # Parse YAML
        try:
            metadata = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {filename}: {e}")

        # Validate required fields
        required_fields = ['name', 'description', 'model']
        for field in required_fields:
            if field not in metadata:
                raise ValueError(f"Missing required field '{field}' in {filename}")

        return AgentTemplate(
            name=metadata['name'],
            description=metadata['description'],
            model=metadata.get('model', 'opus'),
            color=metadata.get('color', 'blue'),
            content=markdown_content.strip(),
            file_path=filename,
            access_control=metadata.get('access_control', None)
        )

    def _parse_github_template_reference(self, template_ref: str) -> Optional[tuple]:
        """
        Parse a GitHub template reference.

        Args:
            template_ref: Template reference (e.g., 'github://development-tools/code-reviewer')

        Returns:
            Tuple of (category, name) or None if not a GitHub reference
        """
        if not template_ref.startswith('github://'):
            return None

        # Remove github:// prefix
        path = template_ref[9:]

        # Split into category and name
        parts = path.split('/')
        if len(parts) != 2:
            raise ValueError(f"Invalid GitHub template reference: {template_ref}. Expected format: github://category/name")

        return parts[0], parts[1]

    def load_template_from_github(self, category: str, name: str) -> AgentTemplate:
        """
        Load a template from GitHub and convert to Blueprint format.

        Args:
            category: Template category (e.g., 'development-tools', 'security')
            name: Template name (e.g., 'code-reviewer')

        Returns:
            AgentTemplate object

        Raises:
            RuntimeError: If GitHub support is not enabled
            TemplateNotFoundError: If template not found on GitHub
        """
        if not self.enable_github:
            raise RuntimeError("GitHub template support is not enabled")

        cache_key = f"github://{category}/{name}"

        # Check cache first
        if cache_key in self._template_cache:
            logger.info(f"Using cached GitHub template: {cache_key}")
            return self._template_cache[cache_key]

        logger.info(f"Downloading template from GitHub: {category}/{name}")

        try:
            # Download template content
            github_content = asyncio.run(
                self.github_downloader.download_template(category, name)
            )

            # Convert to Blueprint format
            blueprint_metadata = self.template_converter.convert_github_to_blueprint(
                github_content,
                category=category,
                file_path=f"{category}/{name}.md"
            )

            # Create AgentTemplate
            template = AgentTemplate(
                name=blueprint_metadata.name,
                description=blueprint_metadata.description,
                model=blueprint_metadata.model,
                color=blueprint_metadata.color,
                content=blueprint_metadata.content,
                file_path=blueprint_metadata.file_path,
                access_control=blueprint_metadata.access_control
            )

            # Cache the template
            self._template_cache[cache_key] = template
            logger.info(f"Successfully loaded GitHub template: {cache_key}")

            # Optionally cache to local filesystem
            self._cache_github_template_to_disk(category, name, blueprint_metadata)

            return template

        except Exception as e:
            logger.error(f"Failed to load GitHub template {category}/{name}: {e}")
            raise

    def _cache_github_template_to_disk(self, category: str, name: str, metadata) -> None:
        """
        Cache a GitHub template to local disk for offline access.

        Args:
            category: Template category
            name: Template name
            metadata: Blueprint template metadata
        """
        try:
            # Create cache directory
            cache_path = self.github_cache_dir / category
            cache_path.mkdir(parents=True, exist_ok=True)

            # Generate full template content
            template_content = self.template_converter.generate_blueprint_template(metadata)

            # Write to file
            file_path = cache_path / f"{name}.md"
            file_path.write_text(template_content, encoding='utf-8')

            logger.info(f"Cached GitHub template to disk: {file_path}")

        except Exception as e:
            logger.warning(f"Failed to cache template to disk: {e}")

    def load_template(self, template_name: str) -> AgentTemplate:
        """
        Load an agent template from WSL or GitHub.

        Supports multiple formats:
        - Simple name: 'code-reviewer' -> loads from WSL
        - GitHub reference: 'github://development-tools/code-reviewer' -> loads from GitHub

        Args:
            template_name: Name or reference of the template

        Returns:
            AgentTemplate object

        Raises:
            FileNotFoundError: If template doesn't exist
            ValueError: If template format is invalid
        """
        # Check if it's a GitHub reference
        github_ref = self._parse_github_template_reference(template_name)

        if github_ref:
            category, name = github_ref
            return self.load_template_from_github(category, name)

        # Check cache first
        if template_name in self._template_cache:
            return self._template_cache[template_name]

        # Try WSL first
        filename = f"{template_name}.md"
        wsl_file_path = f"{self.wsl_agents_path}/{filename}"

        try:
            content = self._read_wsl_file(wsl_file_path)
            template = self._parse_agent_template(content, filename)
            self._template_cache[template_name] = template
            return template

        except RuntimeError as wsl_error:
            # If GitHub is enabled, try loading from GitHub as fallback
            if self.enable_github:
                logger.info(f"WSL template not found, trying GitHub fallback for '{template_name}'")

                # Try common categories
                common_categories = [
                    'development-tools',
                    'development-team',
                    'security',
                    'testing',
                    'data-ai'
                ]

                for category in common_categories:
                    try:
                        return self.load_template_from_github(category, template_name)
                    except Exception:
                        continue

                # If all attempts failed
                logger.error(f"Template '{template_name}' not found in WSL or GitHub")
                raise FileNotFoundError(
                    f"Agent template '{template_name}' not found in WSL or GitHub. "
                    f"WSL error: {wsl_error}"
                )
            else:
                raise FileNotFoundError(f"Agent template '{template_name}' not found in WSL: {wsl_error}")

    def list_available_templates(self) -> List[str]:
        """
        List all available agent templates in WSL.

        Returns:
            List of template names (without .md extension)
        """
        files = self._list_wsl_agents()
        return [f[:-3] for f in files if f.endswith('.md')]  # Remove .md extension

    def create_agent_prompt(
        self,
        template_name: str,
        context: Dict[str, Any],
        role_specialization: Optional[str] = None,
        cahier_content: Optional[str] = None
    ) -> str:
        """
        Create a specialized agent prompt by injecting context into a template.

        Args:
            template_name: Name of the base template to use
            context: Dictionary with context to inject (e.g., task spec, file paths)
            role_specialization: Optional additional role description
            cahier_content: Optional cahier des charges content to inject as context

        Returns:
            Complete agent prompt ready to use

        Example:
            factory = AgentFactory()
            prompt = factory.create_agent_prompt(
                template_name='test-engineer',
                context={
                    'task_id': 'TASK-101',
                    'spec': {...},
                    'worktree_path': '/path/to/worktree'
                },
                role_specialization="Focus exclusively on authentication tests"
            )
        """
        # Load base template
        template = self.load_template(template_name)

        # Build context section
        context_lines = ["# TASK CONTEXT\n"]

        if 'task_id' in context:
            context_lines.append(f"**Task ID**: {context['task_id']}\n")

        if 'domain' in context:
            context_lines.append(f"**Domain**: {context['domain']}\n")

        if 'spec' in context:
            context_lines.append("\n## Task Specification\n")
            spec = context['spec']
            if isinstance(spec, dict):
                context_lines.append(f"**Title**: {spec.get('title', 'N/A')}\n")
                context_lines.append(f"**Description**: {spec.get('description', 'N/A')}\n")

                if 'requirements' in spec:
                    context_lines.append("\n**Requirements**:\n")
                    for req in spec['requirements']:
                        context_lines.append(f"- {req}\n")

                if 'acceptance_criteria' in spec:
                    context_lines.append("\n**Acceptance Criteria**:\n")
                    for criterion in spec['acceptance_criteria']:
                        context_lines.append(f"- {criterion}\n")

                if 'files_scope' in spec:
                    context_lines.append("\n**File Scope**:\n")
                    for file in spec['files_scope']:
                        context_lines.append(f"- {file}\n")

                # Merge and inject access control configuration
                spec_access = spec.get('access', None)
                template_access = template.access_control
                merged_access = merge_access_configs(spec_access, template_access)

                if merged_access and (merged_access.get('allow') or merged_access.get('exclude')):
                    context_lines.append("\n## ACCESS CONTROL RESTRICTIONS\n")
                    context_lines.append("**IMPORTANT**: Your file access is restricted by the following rules:\n\n")

                    if merged_access.get('allow'):
                        context_lines.append("**Allowed Access** (you can ONLY access these paths):\n")
                        for allowed in merged_access['allow']:
                            context_lines.append(f"  ✓ {allowed}\n")
                        context_lines.append("\n")

                    if merged_access.get('exclude'):
                        context_lines.append("**Explicitly EXCLUDED** (you CANNOT access these paths under any circumstances):\n")
                        for excluded in merged_access['exclude']:
                            context_lines.append(f"  ✗ {excluded}\n")
                        context_lines.append("\n")

                    context_lines.append("**CRITICAL**: Exclusions take priority over allows. Any attempt to access excluded paths will be blocked.\n")
                    context_lines.append("If you need access to an excluded path, you must request human approval.\n")

        if 'worktree_path' in context:
            context_lines.append(f"\n**Working Directory**: {context['worktree_path']}\n")
            context_lines.append(f"**IMPORTANT**: All your work must be done in this worktree, not in the main repository.\n")

        if 'branch_name' in context:
            context_lines.append(f"**Git Branch**: {context['branch_name']}\n")

        # Add role specialization if provided
        if role_specialization:
            context_lines.append(f"\n## Role Specialization\n{role_specialization}\n")

        # Assemble final prompt
        prompt_parts = [
            "".join(context_lines),
            "\n---\n",
            template.content,
            "\n\n---\n",
            "**Remember**: Your work is scoped to the task specification above. Stay focused on the requirements and acceptance criteria."
        ]

        base_prompt = "\n".join(prompt_parts)

        # Inject cahier des charges if provided
        if cahier_content:
            task_id = context.get('task_id', 'UNKNOWN')
            return self.inject_cahier_context(base_prompt, cahier_content, task_id)

        return base_prompt

    def inject_cahier_context(
        self,
        base_prompt: str,
        cahier_content: str,
        task_id: str
    ) -> str:
        """
        Inject cahier des charges into agent prompt.

        The cahier des charges (specification document) is injected as context
        to provide the specialist agent with comprehensive analysis and
        recommendations from the analyst phase.

        Args:
            base_prompt: Original prompt from template
            cahier_content: Cahier Markdown content from analyst agent
            task_id: Task ID for context

        Returns:
            Enhanced prompt with cahier injected

        Example:
            factory = AgentFactory()
            enhanced = factory.inject_cahier_context(
                base_prompt="You are a senior engineer...",
                cahier_content="# Cahier des Charges - Security\\n\\n...",
                task_id="TASK-101"
            )
        """
        return f"""{base_prompt}

---

## CAHIER DES CHARGES (Specification Document)

The following cahier des charges has been created by an analyst agent.
Follow its recommendations for architecture, technologies, and best practices.

{cahier_content}

---

**Task ID**: {task_id}

Begin implementation following the cahier's specifications.
"""

    def get_template_info(self, template_name: str) -> Dict[str, Any]:
        """
        Get information about a template without loading full content.

        Args:
            template_name: Name of the template

        Returns:
            Dictionary with template metadata
        """
        template = self.load_template(template_name)

        return {
            'name': template.name,
            'description': template.description,
            'model': template.model,
            'color': template.color,
            'file_path': template.file_path
        }

    def suggest_template_for_role(self, role: str) -> Optional[str]:
        """
        Suggest an appropriate template based on role name.

        Args:
            role: Role description (e.g., 'coder', 'verifier', 'tester')

        Returns:
            Suggested template name or None
        """
        role_mapping = {
            'coder': 'senior-engineer',
            'verifier': 'code-reviewer',
            'tester': 'test-engineer',
            'analyst': 'system-architect',
            'qa': 'qa-specialist',
            'security': 'security-auditor',
            'performance': 'performance-optimizer',
            'docs': 'documentation-writer',
            'devops': 'devops-engineer'
        }

        return role_mapping.get(role.lower())

    def get_merged_access_config(
        self,
        template_name: str,
        spec: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[str]]:
        """
        Get merged access control configuration from template and spec.

        Args:
            template_name: Name of the agent template
            spec: Task specification (may contain 'access' field)

        Returns:
            Merged access configuration with 'allow' and 'exclude' keys
        """
        template = self.load_template(template_name)
        template_access = template.access_control
        spec_access = spec.get('access', None) if spec else None

        return merge_access_configs(spec_access, template_access)


# Convenience function for quick agent creation
def create_specialized_agent(
    role: str,
    task_context: Dict[str, Any],
    specialization: Optional[str] = None
) -> str:
    """
    Quick helper to create a specialized agent prompt.

    Args:
        role: Agent role (coder, verifier, tester, etc.)
        task_context: Task specification and context
        specialization: Additional role specialization

    Returns:
        Complete agent prompt

    Example:
        prompt = create_specialized_agent(
            role='coder',
            task_context={
                'task_id': 'TASK-101',
                'spec': {...}
            }
        )
    """
    factory = AgentFactory()
    template_name = factory.suggest_template_for_role(role)

    if not template_name:
        raise ValueError(f"No template found for role: {role}")

    return factory.create_agent_prompt(template_name, task_context, specialization)
