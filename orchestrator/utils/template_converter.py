"""
Template Converter - Converts GitHub templates to Blueprint format

This module handles the conversion of templates from the claude-code-templates
repository format to the Blueprint AgentTemplate format.
"""

import re
import logging
from typing import Optional, Dict, List
from dataclasses import dataclass
import yaml

logger = logging.getLogger(__name__)


@dataclass
class GitHubTemplateMetadata:
    """Metadata extracted from GitHub template YAML frontmatter"""
    name: str
    description: str
    model: str = "opus"
    tools: Optional[str] = None
    category: Optional[str] = None


@dataclass
class BlueprintTemplateMetadata:
    """Metadata for Blueprint AgentTemplate format"""
    name: str
    description: str
    model: str
    color: str
    content: str
    file_path: str
    access_control: Optional[Dict[str, List[str]]] = None


class TemplateConverter:
    """Converts templates between formats"""

    # Color mapping by category for visual organization
    CATEGORY_COLORS = {
        # Development
        "development-team": "blue",
        "development-tools": "cyan",
        "debugging": "magenta",

        # Testing & Quality
        "testing": "green",
        "performance-testing": "yellow",

        # Security
        "security": "red",
        "compliance": "orange",

        # Data & AI
        "data-ai": "purple",
        "ai-specialists": "violet",

        # Infrastructure
        "devops-infrastructure": "gray",
        "cloud": "lightblue",
        "database": "teal",

        # API & Web
        "api-graphql": "cyan",
        "web-tools": "blue",

        # Documentation
        "documentation": "white",
        "technical-writing": "lightgray",

        # Business
        "business-marketing": "yellow",
        "analytics": "orange",

        # Specialized
        "blockchain-web3": "gold",
        "research": "purple",

        # Default
        "default": "white"
    }

    # Model mapping/normalization
    MODEL_MAPPING = {
        "sonnet": "sonnet",
        "opus": "opus",
        "haiku": "haiku",
        "claude-3-sonnet": "sonnet",
        "claude-3-opus": "opus",
        "claude-3-haiku": "haiku",
    }

    def __init__(self):
        """Initialize the template converter"""
        logger.info("TemplateConverter initialized")

    def parse_github_template(self, content: str) -> GitHubTemplateMetadata:
        """
        Parse GitHub template format (YAML frontmatter + markdown)

        Args:
            content: Raw template content

        Returns:
            Parsed metadata

        Raises:
            ValueError: If template format is invalid
        """
        # Extract YAML frontmatter
        frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)

        if not frontmatter_match:
            raise ValueError("Template does not contain valid YAML frontmatter")

        frontmatter_text = frontmatter_match.group(1)

        try:
            metadata = yaml.safe_load(frontmatter_text)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in frontmatter: {e}")

        # Validate required fields
        if 'name' not in metadata:
            raise ValueError("Template missing required 'name' field")
        if 'description' not in metadata:
            raise ValueError("Template missing required 'description' field")

        return GitHubTemplateMetadata(
            name=metadata['name'],
            description=metadata['description'],
            model=metadata.get('model', 'opus'),
            tools=metadata.get('tools'),
            category=metadata.get('category')
        )

    def extract_content(self, template: str) -> str:
        """
        Extract markdown content (without frontmatter)

        Args:
            template: Raw template content

        Returns:
            Markdown content only
        """
        # Remove YAML frontmatter
        content_match = re.sub(r'^---\s*\n.*?\n---\s*\n', '', template, flags=re.DOTALL)
        return content_match.strip()

    def assign_color_by_category(self, category: Optional[str], name: str) -> str:
        """
        Assign a color based on template category

        Args:
            category: Template category
            name: Template name (used as fallback for category detection)

        Returns:
            Color code
        """
        # Try explicit category first
        if category and category in self.CATEGORY_COLORS:
            return self.CATEGORY_COLORS[category]

        # Try to infer category from name
        name_lower = name.lower()

        for category_key, color in self.CATEGORY_COLORS.items():
            if category_key in name_lower:
                return color

        # Specific keyword matching
        if any(kw in name_lower for kw in ['test', 'qa', 'quality']):
            return "green"
        elif any(kw in name_lower for kw in ['security', 'audit', 'pentest']):
            return "red"
        elif any(kw in name_lower for kw in ['dev', 'code', 'engineer']):
            return "blue"
        elif any(kw in name_lower for kw in ['data', 'ml', 'ai']):
            return "purple"
        elif any(kw in name_lower for kw in ['doc', 'write']):
            return "white"

        # Default
        return self.CATEGORY_COLORS["default"]

    def normalize_model(self, model: str) -> str:
        """
        Normalize model name

        Args:
            model: Model name from template

        Returns:
            Normalized model name
        """
        model_lower = model.lower()
        return self.MODEL_MAPPING.get(model_lower, "opus")

    def convert_github_to_blueprint(
        self,
        content: str,
        category: Optional[str] = None,
        file_path: Optional[str] = None,
        access_control: Optional[Dict[str, List[str]]] = None
    ) -> BlueprintTemplateMetadata:
        """
        Convert GitHub template format to Blueprint format

        Args:
            content: Raw GitHub template content
            category: Template category (for color assignment)
            file_path: Path where template will be saved
            access_control: Optional access control configuration

        Returns:
            Blueprint template metadata

        Raises:
            ValueError: If conversion fails
        """
        try:
            # Parse GitHub format
            github_metadata = self.parse_github_template(content)

            # Extract content
            markdown_content = self.extract_content(content)

            # Determine category
            effective_category = category or github_metadata.category

            # Assign color
            color = self.assign_color_by_category(effective_category, github_metadata.name)

            # Normalize model
            model = self.normalize_model(github_metadata.model)

            # Generate file path if not provided
            if file_path is None:
                file_path = f"templates/agents/{github_metadata.name}.md"

            # Create Blueprint metadata
            blueprint_metadata = BlueprintTemplateMetadata(
                name=github_metadata.name,
                description=github_metadata.description,
                model=model,
                color=color,
                content=markdown_content,
                file_path=file_path,
                access_control=access_control
            )

            logger.info(
                f"Converted template '{github_metadata.name}' "
                f"(model={model}, color={color}, category={effective_category})"
            )

            return blueprint_metadata

        except Exception as e:
            logger.error(f"Error converting template: {e}")
            raise

    def generate_blueprint_template(self, metadata: BlueprintTemplateMetadata) -> str:
        """
        Generate Blueprint template file content from metadata

        Args:
            metadata: Blueprint template metadata

        Returns:
            Full template content with YAML frontmatter
        """
        # Build frontmatter
        frontmatter = {
            'name': metadata.name,
            'description': metadata.description,
            'model': metadata.model,
            'color': metadata.color
        }

        if metadata.access_control:
            frontmatter['access_control'] = metadata.access_control

        # Generate YAML
        yaml_content = yaml.dump(frontmatter, sort_keys=False, allow_unicode=True)

        # Combine frontmatter and content
        template_content = f"---\n{yaml_content}---\n\n{metadata.content}"

        return template_content

    def convert_and_generate(
        self,
        github_content: str,
        category: Optional[str] = None,
        access_control: Optional[Dict[str, List[str]]] = None
    ) -> str:
        """
        Convert GitHub template and generate Blueprint template content

        Args:
            github_content: Raw GitHub template
            category: Template category
            access_control: Access control configuration

        Returns:
            Blueprint template content ready to save
        """
        metadata = self.convert_github_to_blueprint(
            github_content,
            category=category,
            access_control=access_control
        )

        return self.generate_blueprint_template(metadata)

    def extract_tools_list(self, content: str) -> Optional[List[str]]:
        """
        Extract tools list from GitHub template

        Args:
            content: Raw template content

        Returns:
            List of tools, or None if not specified
        """
        metadata = self.parse_github_template(content)

        if metadata.tools:
            # Split by comma and clean up
            tools = [tool.strip() for tool in metadata.tools.split(',')]
            return tools

        return None

    def validate_template(self, content: str) -> bool:
        """
        Validate template format

        Args:
            content: Template content

        Returns:
            True if valid, False otherwise
        """
        try:
            self.parse_github_template(content)
            return True
        except ValueError as e:
            logger.warning(f"Template validation failed: {e}")
            return False


class TemplateMerger:
    """Merges multiple templates or template configurations"""

    @staticmethod
    def merge_access_control(
        template_ac: Optional[Dict[str, List[str]]],
        task_ac: Optional[Dict[str, List[str]]]
    ) -> Optional[Dict[str, List[str]]]:
        """
        Merge access control from template and task spec

        Args:
            template_ac: Access control from template
            task_ac: Access control from task specification

        Returns:
            Merged access control configuration
        """
        if not template_ac and not task_ac:
            return None

        merged = {
            'allow': [],
            'exclude': []
        }

        # Merge allow lists
        if template_ac and 'allow' in template_ac:
            merged['allow'].extend(template_ac['allow'])
        if task_ac and 'allow' in task_ac:
            merged['allow'].extend(task_ac['allow'])

        # Merge exclude lists
        if template_ac and 'exclude' in template_ac:
            merged['exclude'].extend(template_ac['exclude'])
        if task_ac and 'exclude' in task_ac:
            merged['exclude'].extend(task_ac['exclude'])

        # Remove duplicates while preserving order
        merged['allow'] = list(dict.fromkeys(merged['allow']))
        merged['exclude'] = list(dict.fromkeys(merged['exclude']))

        return merged if merged['allow'] or merged['exclude'] else None


if __name__ == "__main__":
    # Example usage
    converter = TemplateConverter()

    # Example GitHub template
    github_template = """---
name: code-reviewer
description: Expert code review specialist for quality, security, and maintainability
tools: Read, Write, Edit, Bash, Grep
model: sonnet
---

# Code Review Expert

You are an expert code reviewer specializing in...

## Responsibilities
- Review code for quality
- Check for security issues
- Ensure best practices
"""

    # Convert to Blueprint format
    blueprint_metadata = converter.convert_github_to_blueprint(
        github_template,
        category="development-tools"
    )

    print("Converted Metadata:")
    print(f"  Name: {blueprint_metadata.name}")
    print(f"  Model: {blueprint_metadata.model}")
    print(f"  Color: {blueprint_metadata.color}")
    print(f"  Description: {blueprint_metadata.description}")

    # Generate Blueprint template file
    blueprint_content = converter.generate_blueprint_template(blueprint_metadata)
    print("\nGenerated Blueprint Template:")
    print(blueprint_content[:300])
