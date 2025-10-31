"""
Agent Factory - Creates agent instances from templates.

This module reads agent templates from ~/.claude/agents/ (WSL) and creates
specialized agent instances with injected context for specific tasks.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import yaml


@dataclass
class AgentTemplate:
    """Represents an agent template loaded from ~/.claude/agents/"""
    name: str
    description: str
    model: str
    color: str
    content: str
    file_path: str


class AgentFactory:
    """Creates agent instances from templates stored in WSL"""

    def __init__(self, wsl_agents_path: str = "~/.claude/agents"):
        """
        Initialize the factory.

        Args:
            wsl_agents_path: Path to agents directory in WSL (default: ~/.claude/agents)
        """
        self.wsl_agents_path = wsl_agents_path
        self._template_cache: Dict[str, AgentTemplate] = {}

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
            file_path=filename
        )

    def load_template(self, template_name: str) -> AgentTemplate:
        """
        Load an agent template from WSL.

        Args:
            template_name: Name of the template (e.g., 'code-reviewer', 'test-engineer')

        Returns:
            AgentTemplate object

        Raises:
            FileNotFoundError: If template doesn't exist
            ValueError: If template format is invalid
        """
        # Check cache first
        if template_name in self._template_cache:
            return self._template_cache[template_name]

        # Construct file path
        filename = f"{template_name}.md"
        wsl_file_path = f"{self.wsl_agents_path}/{filename}"

        # Read template file
        try:
            content = self._read_wsl_file(wsl_file_path)
        except RuntimeError as e:
            raise FileNotFoundError(f"Agent template '{template_name}' not found in WSL: {e}")

        # Parse and cache
        template = self._parse_agent_template(content, filename)
        self._template_cache[template_name] = template

        return template

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
        role_specialization: Optional[str] = None
    ) -> str:
        """
        Create a specialized agent prompt by injecting context into a template.

        Args:
            template_name: Name of the base template to use
            context: Dictionary with context to inject (e.g., task spec, file paths)
            role_specialization: Optional additional role description

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

        return "\n".join(prompt_parts)

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
