"""
Template Manager - Advanced template management and discovery

This module provides advanced template management capabilities including:
- Template registry and cataloging
- Template discovery and search
- Template versioning and updates
- Multi-source template management
"""

import logging
import json
from typing import List, Dict, Optional, Any
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import asyncio
import httpx

from orchestrator.utils.template_downloader import GitHubTemplateDownloader, MultiSourceDownloader
from orchestrator.utils.template_converter import TemplateConverter

logger = logging.getLogger(__name__)


@dataclass
class TemplateMetadata:
    """Metadata for a template"""
    name: str
    category: str
    description: str
    model: str
    source: str  # 'local', 'github', 'custom'
    version: Optional[str] = None
    tools: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    popularity: int = 0
    last_updated: Optional[str] = None
    download_url: Optional[str] = None


@dataclass
class TemplateSearchResult:
    """Search result for template queries"""
    metadata: TemplateMetadata
    relevance_score: float
    matched_fields: List[str]


class TemplateRegistry:
    """Registry for managing and discovering templates"""

    CATALOG_API_URL = "https://aitmpl.com/api/agents.json"
    GITHUB_API_URL = "https://api.github.com/repos/davila7/claude-code-templates/contents/cli-tool/components/agents"

    def __init__(
        self,
        cache_file: Optional[Path] = None,
        cache_duration_hours: int = 24
    ):
        """
        Initialize the template registry

        Args:
            cache_file: Path to cache file for template catalog
            cache_duration_hours: How long to cache the catalog
        """
        self.cache_file = cache_file or Path("templates/catalog.json")
        self.cache_duration = timedelta(hours=cache_duration_hours)
        self._catalog: List[TemplateMetadata] = []
        self._last_refresh: Optional[datetime] = None

        logger.info("TemplateRegistry initialized")

    async def refresh_catalog(self, force: bool = False) -> bool:
        """
        Refresh the template catalog from remote sources

        Args:
            force: Force refresh even if cache is valid

        Returns:
            True if catalog was refreshed, False if using cached data
        """
        # Check if we need to refresh
        if not force and self._is_cache_valid():
            logger.info("Using cached catalog (still valid)")
            return False

        logger.info("Refreshing template catalog from remote sources")

        try:
            # Try to fetch from API endpoint first
            catalog_data = await self._fetch_from_api()

            if not catalog_data:
                # Fallback to GitHub API
                catalog_data = await self._fetch_from_github_api()

            if catalog_data:
                self._catalog = catalog_data
                self._last_refresh = datetime.now()
                self._save_cache()
                logger.info(f"Catalog refreshed: {len(self._catalog)} templates")
                return True
            else:
                logger.warning("Failed to refresh catalog from all sources")
                # Try to load from cache file
                self._load_cache()
                return False

        except Exception as e:
            logger.error(f"Error refreshing catalog: {e}")
            # Try to load from cache file
            self._load_cache()
            return False

    async def _fetch_from_api(self) -> Optional[List[TemplateMetadata]]:
        """
        Fetch template catalog from API endpoint

        Returns:
            List of template metadata or None
        """
        try:
            logger.info(f"Fetching catalog from {self.CATALOG_API_URL}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.CATALOG_API_URL)
                response.raise_for_status()

                data = response.json()

                # Parse API response to TemplateMetadata
                catalog = []
                for item in data:
                    metadata = TemplateMetadata(
                        name=item.get('name', ''),
                        category=item.get('category', 'uncategorized'),
                        description=item.get('description', ''),
                        model=item.get('model', 'opus'),
                        source='github',
                        version=item.get('version'),
                        tools=item.get('tools', '').split(', ') if item.get('tools') else None,
                        tags=item.get('tags', []),
                        popularity=item.get('downloads', 0),
                        last_updated=item.get('updated_at'),
                        download_url=item.get('url')
                    )
                    catalog.append(metadata)

                logger.info(f"Fetched {len(catalog)} templates from API")
                return catalog

        except Exception as e:
            logger.warning(f"Failed to fetch from API: {e}")
            return None

    async def _fetch_from_github_api(self) -> Optional[List[TemplateMetadata]]:
        """
        Fetch template catalog by listing GitHub repository contents

        Returns:
            List of template metadata or None
        """
        try:
            logger.info(f"Fetching catalog from GitHub API")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.GITHUB_API_URL)
                response.raise_for_status()

                categories = response.json()
                catalog = []

                # Iterate through categories
                for category_item in categories:
                    if category_item['type'] != 'dir':
                        continue

                    category_name = category_item['name']
                    category_url = category_item['url']

                    # List templates in this category
                    cat_response = await client.get(category_url)
                    cat_response.raise_for_status()

                    templates = cat_response.json()

                    for template_item in templates:
                        if template_item['type'] != 'file' or not template_item['name'].endswith('.md'):
                            continue

                        template_name = template_item['name'].replace('.md', '')

                        metadata = TemplateMetadata(
                            name=template_name,
                            category=category_name,
                            description=f"{template_name} template from {category_name}",
                            model='opus',
                            source='github',
                            download_url=template_item['download_url']
                        )
                        catalog.append(metadata)

                logger.info(f"Fetched {len(catalog)} templates from GitHub API")
                return catalog

        except Exception as e:
            logger.warning(f"Failed to fetch from GitHub API: {e}")
            return None

    def _is_cache_valid(self) -> bool:
        """Check if cached catalog is still valid"""
        if not self._last_refresh:
            return False

        age = datetime.now() - self._last_refresh
        return age < self.cache_duration

    def _save_cache(self) -> None:
        """Save catalog to cache file"""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)

            cache_data = {
                'last_refresh': self._last_refresh.isoformat() if self._last_refresh else None,
                'catalog': [asdict(item) for item in self._catalog]
            }

            self.cache_file.write_text(json.dumps(cache_data, indent=2), encoding='utf-8')
            logger.info(f"Saved catalog cache to {self.cache_file}")

        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def _load_cache(self) -> bool:
        """Load catalog from cache file"""
        try:
            if not self.cache_file.exists():
                logger.warning("Cache file does not exist")
                return False

            cache_data = json.loads(self.cache_file.read_text(encoding='utf-8'))

            self._last_refresh = datetime.fromisoformat(cache_data['last_refresh']) if cache_data.get('last_refresh') else None
            self._catalog = [TemplateMetadata(**item) for item in cache_data['catalog']]

            logger.info(f"Loaded {len(self._catalog)} templates from cache")
            return True

        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            return False

    async def get_catalog(self, auto_refresh: bool = True) -> List[TemplateMetadata]:
        """
        Get the template catalog

        Args:
            auto_refresh: Automatically refresh if cache is invalid

        Returns:
            List of template metadata
        """
        if auto_refresh and not self._is_cache_valid():
            await self.refresh_catalog()
        elif not self._catalog:
            # Try to load from cache
            if not self._load_cache():
                # If no cache, refresh
                await self.refresh_catalog()

        return self._catalog

    async def search_templates(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        model: Optional[str] = None,
        tags: Optional[List[str]] = None,
        min_relevance: float = 0.0
    ) -> List[TemplateSearchResult]:
        """
        Search for templates

        Args:
            query: Search query (matches name and description)
            category: Filter by category
            model: Filter by model
            tags: Filter by tags
            min_relevance: Minimum relevance score

        Returns:
            List of search results sorted by relevance
        """
        catalog = await self.get_catalog()
        results = []

        for template in catalog:
            matched_fields = []
            score = 0.0

            # Category filter
            if category and template.category != category:
                continue

            # Model filter
            if model and template.model != model:
                continue

            # Tags filter
            if tags:
                if not template.tags or not any(tag in template.tags for tag in tags):
                    continue
                matched_fields.append('tags')
                score += 0.3

            # Query matching
            if query:
                query_lower = query.lower()

                # Exact name match (highest score)
                if template.name.lower() == query_lower:
                    score += 1.0
                    matched_fields.append('name')
                # Partial name match
                elif query_lower in template.name.lower():
                    score += 0.7
                    matched_fields.append('name')

                # Description match
                if query_lower in template.description.lower():
                    score += 0.5
                    matched_fields.append('description')

                # Category match
                if query_lower in template.category.lower():
                    score += 0.3
                    matched_fields.append('category')

            else:
                # If no query, give base score
                score = 0.5

            # Popularity boost
            if template.popularity > 0:
                score += min(template.popularity / 1000, 0.2)  # Up to 0.2 boost

            # Only include if meets minimum relevance
            if score >= min_relevance:
                results.append(TemplateSearchResult(
                    metadata=template,
                    relevance_score=score,
                    matched_fields=matched_fields
                ))

        # Sort by relevance
        results.sort(key=lambda x: x.relevance_score, reverse=True)

        logger.info(f"Search found {len(results)} templates (query='{query}', category={category})")
        return results

    async def get_by_category(self, category: str) -> List[TemplateMetadata]:
        """
        Get all templates in a category

        Args:
            category: Category name

        Returns:
            List of template metadata
        """
        catalog = await self.get_catalog()
        return [t for t in catalog if t.category == category]

    async def get_by_name(self, name: str) -> Optional[TemplateMetadata]:
        """
        Get a template by exact name

        Args:
            name: Template name

        Returns:
            Template metadata or None
        """
        catalog = await self.get_catalog()
        for template in catalog:
            if template.name == name:
                return template
        return None

    async def list_categories(self) -> List[str]:
        """
        List all available categories

        Returns:
            List of category names
        """
        catalog = await self.get_catalog()
        categories = set(t.category for t in catalog)
        return sorted(categories)

    async def suggest_for_domain(self, domain: str) -> List[TemplateMetadata]:
        """
        Suggest templates for a specific domain

        Args:
            domain: Domain name (e.g., 'authentication', 'blockchain', 'ml')

        Returns:
            List of recommended templates
        """
        # Domain to category/query mapping
        domain_mapping = {
            'authentication': {'query': 'security auth', 'categories': ['security']},
            'security': {'query': 'security audit', 'categories': ['security']},
            'blockchain': {'query': 'blockchain smart contract', 'categories': ['blockchain-web3']},
            'ml': {'query': 'machine learning ai', 'categories': ['data-ai', 'ai-specialists']},
            'database': {'query': 'database', 'categories': ['database']},
            'api': {'query': 'api rest graphql', 'categories': ['api-graphql']},
            'frontend': {'query': 'frontend react ui', 'categories': ['web-tools', 'development-team']},
            'backend': {'query': 'backend server', 'categories': ['development-team']},
            'devops': {'query': 'devops cloud deployment', 'categories': ['devops-infrastructure']},
            'testing': {'query': 'test qa', 'categories': ['testing', 'development-tools']},
            'performance': {'query': 'performance optimization', 'categories': ['performance-testing']},
        }

        mapping = domain_mapping.get(domain.lower())

        if not mapping:
            # Generic search
            results = await self.search_templates(query=domain, min_relevance=0.3)
        else:
            # Targeted search
            results = await self.search_templates(
                query=mapping.get('query'),
                min_relevance=0.3
            )

            # Also get templates from relevant categories
            for category in mapping.get('categories', []):
                cat_templates = await self.get_by_category(category)
                for template in cat_templates:
                    # Avoid duplicates
                    if not any(r.metadata.name == template.name for r in results):
                        results.append(TemplateSearchResult(
                            metadata=template,
                            relevance_score=0.6,
                            matched_fields=['category']
                        ))

        # Return top 5 suggestions
        return [r.metadata for r in sorted(results, key=lambda x: x.relevance_score, reverse=True)[:5]]


class TemplateManager:
    """High-level template management with discovery and caching"""

    def __init__(
        self,
        cache_dir: Path = Path("templates"),
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the template manager

        Args:
            cache_dir: Directory for caching templates
            config: Configuration dictionary
        """
        self.cache_dir = cache_dir
        self.config = config or {}

        # Initialize components
        self.registry = TemplateRegistry(
            cache_file=cache_dir / "catalog.json",
            cache_duration_hours=self.config.get('cache_duration_hours', 24)
        )

        self.downloader = MultiSourceDownloader()
        self.converter = TemplateConverter()

        logger.info("TemplateManager initialized")

    async def discover_templates(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[TemplateMetadata]:
        """
        Discover available templates

        Args:
            query: Optional search query
            category: Optional category filter

        Returns:
            List of template metadata
        """
        if query or category:
            results = await self.registry.search_templates(query=query, category=category)
            return [r.metadata for r in results]
        else:
            return await self.registry.get_catalog()

    async def sync_templates(self, templates: List[str]) -> Dict[str, bool]:
        """
        Sync specified templates to local cache

        Args:
            templates: List of template references (category/name)

        Returns:
            Dictionary mapping template names to success status
        """
        results = {}

        for template_ref in templates:
            try:
                parts = template_ref.split('/')
                if len(parts) != 2:
                    logger.warning(f"Invalid template reference: {template_ref}")
                    results[template_ref] = False
                    continue

                category, name = parts

                # Download template
                content = await self.downloader.download_template(category, name)

                # Convert to Blueprint format
                metadata = self.converter.convert_github_to_blueprint(content, category=category)

                # Save to cache
                template_content = self.converter.generate_blueprint_template(metadata)
                cache_path = self.cache_dir / category
                cache_path.mkdir(parents=True, exist_ok=True)

                file_path = cache_path / f"{name}.md"
                file_path.write_text(template_content, encoding='utf-8')

                logger.info(f"Synced template {template_ref} to {file_path}")
                results[template_ref] = True

            except Exception as e:
                logger.error(f"Failed to sync template {template_ref}: {e}")
                results[template_ref] = False

        return results

    async def get_template_recommendations(self, domain: str) -> List[TemplateMetadata]:
        """
        Get template recommendations for a domain

        Args:
            domain: Domain name

        Returns:
            List of recommended templates
        """
        return await self.registry.suggest_for_domain(domain)


if __name__ == "__main__":
    # Example usage
    async def main():
        manager = TemplateManager()

        # Refresh catalog
        await manager.registry.refresh_catalog()

        # Search for templates
        results = await manager.registry.search_templates(query="security", min_relevance=0.3)
        print(f"\nFound {len(results)} security-related templates:")
        for result in results[:5]:
            print(f"  - {result.metadata.name} ({result.metadata.category})")
            print(f"    Relevance: {result.relevance_score:.2f}")
            print(f"    Matched: {result.matched_fields}")

        # Get recommendations for a domain
        recommendations = await manager.get_template_recommendations("blockchain")
        print(f"\nRecommendations for 'blockchain' domain:")
        for rec in recommendations:
            print(f"  - {rec.name} ({rec.category})")

        # List categories
        categories = await manager.registry.list_categories()
        print(f"\nAvailable categories: {categories}")

    asyncio.run(main())
