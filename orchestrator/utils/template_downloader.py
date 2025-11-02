"""
Template Downloader - Downloads agent templates from GitHub repositories

This module provides functionality to download agent templates from the
claude-code-templates repository and other sources.
"""

import logging
from typing import Optional, Dict, List
from dataclasses import dataclass
from pathlib import Path
import httpx
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class TemplateSource:
    """Configuration for a template source"""
    name: str
    base_url: str
    enabled: bool = True
    timeout: int = 30
    cache_duration: int = 86400  # 24 hours in seconds


class GitHubTemplateDownloader:
    """Downloads templates from GitHub repositories"""

    # Default GitHub repository for templates
    DEFAULT_REPO = "davila7/claude-code-templates"
    DEFAULT_BRANCH = "main"
    DEFAULT_BASE_PATH = "cli-tool/components/agents"

    def __init__(
        self,
        repository: str = DEFAULT_REPO,
        branch: str = DEFAULT_BRANCH,
        base_path: str = DEFAULT_BASE_PATH,
        timeout: int = 30
    ):
        """
        Initialize the GitHub template downloader

        Args:
            repository: GitHub repository in format "owner/repo"
            branch: Git branch to download from
            base_path: Base path within the repository
            timeout: HTTP request timeout in seconds
        """
        self.repository = repository
        self.branch = branch
        self.base_path = base_path
        self.timeout = timeout
        self.base_url = f"https://raw.githubusercontent.com/{repository}/{branch}/{base_path}"

        logger.info(f"GitHubTemplateDownloader initialized for {repository}")

    async def download_template(self, category: str, name: str) -> str:
        """
        Download a template from GitHub

        Args:
            category: Template category (e.g., "development-tools", "security")
            name: Template name (without .md extension)

        Returns:
            Template content as string

        Raises:
            httpx.HTTPStatusError: If the request fails
            httpx.TimeoutException: If the request times out
        """
        url = f"{self.base_url}/{category}/{name}.md"

        logger.info(f"Downloading template from {url}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()

                content = response.text
                logger.info(f"Successfully downloaded template {category}/{name} ({len(content)} bytes)")
                return content

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.error(f"Template not found: {category}/{name}")
                raise TemplateNotFoundError(f"Template {category}/{name} not found at {url}")
            else:
                logger.error(f"HTTP error downloading template: {e}")
                raise

        except httpx.TimeoutException:
            logger.error(f"Timeout downloading template {category}/{name}")
            raise

        except Exception as e:
            logger.error(f"Unexpected error downloading template: {e}")
            raise

    async def list_category_templates(self, category: str) -> List[str]:
        """
        List all templates in a category using GitHub API

        Args:
            category: Template category

        Returns:
            List of template names (without .md extension)
        """
        api_url = f"https://api.github.com/repos/{self.repository}/contents/{self.base_path}/{category}"

        logger.info(f"Listing templates in category {category}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(api_url)
                response.raise_for_status()

                files = response.json()
                templates = [
                    file['name'].replace('.md', '')
                    for file in files
                    if file['type'] == 'file' and file['name'].endswith('.md')
                ]

                logger.info(f"Found {len(templates)} templates in {category}")
                return templates

        except Exception as e:
            logger.error(f"Error listing templates in category {category}: {e}")
            return []

    async def download_and_cache(
        self,
        category: str,
        name: str,
        cache_dir: Path
    ) -> Path:
        """
        Download a template and cache it locally

        Args:
            category: Template category
            name: Template name
            cache_dir: Directory to cache templates

        Returns:
            Path to cached template file
        """
        # Create cache directory structure
        category_dir = cache_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)

        template_path = category_dir / f"{name}.md"

        # Download template
        content = await self.download_template(category, name)

        # Save to cache
        template_path.write_text(content, encoding='utf-8')
        logger.info(f"Cached template to {template_path}")

        return template_path

    def get_template_url(self, category: str, name: str) -> str:
        """
        Get the full URL for a template

        Args:
            category: Template category
            name: Template name

        Returns:
            Full URL to the template
        """
        return f"{self.base_url}/{category}/{name}.md"


class MultiSourceDownloader:
    """Manages downloads from multiple template sources"""

    def __init__(self):
        self.sources: Dict[str, GitHubTemplateDownloader] = {}
        self._add_default_source()

    def _add_default_source(self):
        """Add the default claude-code-templates source"""
        self.add_source(
            "default",
            GitHubTemplateDownloader()
        )

    def add_source(self, name: str, downloader: GitHubTemplateDownloader):
        """
        Add a template source

        Args:
            name: Source identifier
            downloader: Configured GitHubTemplateDownloader instance
        """
        self.sources[name] = downloader
        logger.info(f"Added template source: {name}")

    async def download_template(
        self,
        category: str,
        name: str,
        source: str = "default"
    ) -> str:
        """
        Download a template from a specific source

        Args:
            category: Template category
            name: Template name
            source: Source identifier

        Returns:
            Template content

        Raises:
            ValueError: If source is not configured
        """
        if source not in self.sources:
            raise ValueError(f"Unknown template source: {source}")

        downloader = self.sources[source]
        return await downloader.download_template(category, name)

    async def try_all_sources(self, category: str, name: str) -> Optional[str]:
        """
        Try to download a template from all sources

        Args:
            category: Template category
            name: Template name

        Returns:
            Template content from first successful source, or None
        """
        for source_name, downloader in self.sources.items():
            try:
                logger.info(f"Trying source {source_name} for {category}/{name}")
                content = await downloader.download_template(category, name)
                logger.info(f"Successfully downloaded from {source_name}")
                return content
            except Exception as e:
                logger.warning(f"Failed to download from {source_name}: {e}")
                continue

        logger.error(f"Failed to download {category}/{name} from all sources")
        return None


class TemplateNotFoundError(Exception):
    """Raised when a template is not found"""
    pass


# Utility function for synchronous usage
def download_template_sync(category: str, name: str) -> str:
    """
    Synchronous wrapper for downloading a template

    Args:
        category: Template category
        name: Template name

    Returns:
        Template content
    """
    downloader = GitHubTemplateDownloader()
    return asyncio.run(downloader.download_template(category, name))


if __name__ == "__main__":
    # Example usage
    async def main():
        downloader = GitHubTemplateDownloader()

        # Download a specific template
        try:
            content = await downloader.download_template("development-tools", "code-reviewer")
            print(f"Downloaded template: {len(content)} bytes")
            print(content[:200])  # Print first 200 characters
        except Exception as e:
            print(f"Error: {e}")

        # List templates in a category
        templates = await downloader.list_category_templates("development-tools")
        print(f"\nAvailable templates in development-tools: {templates}")

    asyncio.run(main())
