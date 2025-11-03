"""
Phase 0: Master Analyst + Analyst Agents

The Master Analyst receives a high-level business requirement and creates
multiple specialist analyst agents. Each analyst generates a "cahier des charges"
(specification document) in Markdown format.

This is the new "generator" phase that creates contextual specifications.
"""

import asyncio
import json
import hashlib
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

from orchestrator.agent_factory import AgentFactory
from orchestrator.utils.logger import PipelineLogger
from orchestrator.db import Database, AgentStatus, TaskStatus
from orchestrator.agents.gemini_researcher import GeminiResearcher


@dataclass
class Domain:
    """Represents a domain identified by the master analyst"""
    name: str
    description: str
    analyst_template: str
    priority: str = "medium"
    complexity: str = "moderate"
    research_queries: Optional[List[str]] = None


class AnalystAgent:
    """
    Specialist analyst agent that creates a cahier des charges for a domain.

    Each analyst:
    1. Analyzes the existing codebase for the domain
    2. Optionally performs external research (via Gemini)
    3. Generates a detailed cahier des charges in Markdown
    4. Stores the cahier in cahiers_charges/{domain}/
    """

    def __init__(
        self,
        domain: Domain,
        requirement: str,
        config: Dict[str, Any],
        logger: PipelineLogger,
        db: Database,
        agent_factory: AgentFactory,
        gemini_researcher: Optional[GeminiResearcher] = None
    ):
        """
        Initialize an analyst agent.

        Args:
            domain: Domain this analyst specializes in
            requirement: Original user requirement
            config: Pipeline configuration
            logger: Logger instance
            db: Database instance
            agent_factory: Agent factory for prompt generation
            gemini_researcher: Optional Gemini researcher for external research
        """
        self.domain = domain
        self.requirement = requirement
        self.config = config
        self.logger = logger
        self.db = db
        self.factory = agent_factory
        self.gemini = gemini_researcher
        self.agent_id = f"Analyst-{domain.name}"
        self.phase0_config = config.get('phase0', {})

    def _create_analyst_prompt(self, research_results: Optional[Dict[str, Any]] = None) -> str:
        """
        Create the prompt for this analyst agent.

        Args:
            research_results: Optional research results from Gemini

        Returns:
            Formatted prompt
        """
        prompt = f"""# ANALYST AGENT - {self.domain.name.upper()}

You are a specialist analyst agent responsible for the **{self.domain.name}** domain.

## CONTEXT

### Original User Requirement
{self.requirement}

### Your Domain
**Name**: {self.domain.name}
**Description**: {self.domain.description}
**Priority**: {self.domain.priority}
**Complexity**: {self.domain.complexity}

## YOUR TASK

Create a comprehensive "cahier des charges" (specification document) for implementing this domain.

Your cahier should include:

### 1. Contexte et Analyse
- Analyse du besoin utilisateur pour ce domaine spécifique
- Code existant pertinent (si applicable)
- Architecture recommandée

### 2. Objectifs
- Liste claire des objectifs à atteindre
- Résultats attendus

### 3. Spécifications Techniques
- Requis techniques détaillés
- Technologies et bibliothèques à utiliser
- Patterns et architectures recommandés

### 4. Fichiers et Structure
- Fichiers à créer ou modifier
- Structure de dossiers recommandée
- Conventions de nommage

### 5. Dépendances
- Bibliothèques externes nécessaires
- Dépendances avec d'autres domaines
- Prérequis techniques

### 6. Critères d'Acceptation
- Liste de vérification pour validation
- Tests requis
- Critères de performance

### 7. Considérations de Sécurité
- Vulnérabilités potentielles
- Mesures de protection requises
- Bonnes pratiques de sécurité
"""

        # Add research results if available
        if research_results and research_results.get('results'):
            prompt += f"""

### 8. Recherches Externes (Gemini)

Les recherches suivantes ont été effectuées pour enrichir ce cahier:

"""
            for idx, result in enumerate(research_results['results'], 1):
                prompt += f"""
#### Recherche {idx}: {result.get('query', 'N/A')}

**Sources**: {', '.join(research_results.get('sources', []))}

**Résultats**:
"""
                for finding in result.get('findings', []):
                    prompt += f"- **{finding.get('title', 'N/A')}**: {finding.get('summary', 'N/A')}\n"

        prompt += """

## OUTPUT FORMAT

Generate a well-structured Markdown document following this template:

```markdown
# Cahier des Charges - {Domain Name}

**Domaine**: {Domain}
**Priorité**: {Priority}
**Complexité**: {Complexity}
**Date de création**: {Date}

## 1. Contexte et Analyse

[Your analysis here]

## 2. Objectifs

- [Objective 1]
- [Objective 2]
...

## 3. Spécifications Techniques

### Technologies
- [Tech 1]
- [Tech 2]

### Architecture
[Architecture description]

## 4. Fichiers et Structure

```
path/to/file1.ext
path/to/file2.ext
```

## 5. Dépendances

### Bibliothèques
- [Library 1]: [Purpose]
- [Library 2]: [Purpose]

### Dépendances inter-domaines
- Dépend de: [Other Domain]

## 6. Critères d'Acceptation

- [ ] Critère 1
- [ ] Critère 2
...

## 7. Sécurité

- [Security consideration 1]
- [Security consideration 2]

## 8. Notes Techniques

[Additional notes]
```

## GUIDELINES

- Be specific and detailed
- Include code examples where relevant
- Consider edge cases and error handling
- Think about scalability and maintainability
- Reference best practices and industry standards
- Be pragmatic - balance ideal vs practical

IMPORTANT: Return ONLY the Markdown cahier des charges, no other text.
"""

        return prompt

    async def analyze_and_create_cahier(self) -> Optional[Dict[str, Any]]:
        """
        Analyze the domain and create a cahier des charges.

        Returns:
            Dict with cahier_path and task_ids, or None if failed
        """
        self.logger.info(f"[{self.agent_id}] Starting analysis for domain: {self.domain.name}")

        # Register agent in database with access control
        # Analysts have restricted access: only cahiers_charges directory
        cahiers_dir = self.config.get('phase0', {}).get('cahiers_charges_dir', 'cahiers_charges')

        await self.db.create_agent(
            agent_id=self.agent_id,
            task_id=f"DOMAIN-{self.domain.name}",
            role="analyst",
            template_name=self.domain.analyst_template,
            allow_paths=[f"{cahiers_dir}/**/*"],  # Only access to cahiers directory
            exclude_paths=[".git/**", ".worktrees/**", "*.db", "**/.env"],  # Standard exclusions
            access_mode='block',  # Strict enforcement for analysts
            worktree_path=None  # Analysts don't work in worktrees
        )
        await self.db.update_agent_status(self.agent_id, AgentStatus.WORKING)

        try:
            # Step 1: Perform external research if Gemini is enabled
            research_results = None
            if self.gemini and self.gemini.is_enabled() and self.domain.research_queries:
                self.logger.info(f"[{self.agent_id}] Performing external research...")
                research_results = await self._perform_research()

            # Step 2: Create analyst prompt
            prompt = self._create_analyst_prompt(research_results)

            self.logger.debug(f"[{self.agent_id}] Generated prompt ({len(prompt)} chars)")

            # Step 3: Simulate cahier generation
            # TODO: Replace with actual AI model call
            cahier_content, tasks_data = await self._simulate_cahier_generation()

            # Step 4: Save cahier to file
            cahier_path = await self._save_cahier(cahier_content)

            # Step 5: Register cahier in database
            cahier_id = f"CAHIER-{self.domain.name}"
            content_hash = hashlib.md5(cahier_content.encode()).hexdigest()

            await self.db.create_cahier(
                cahier_id=cahier_id,
                domain=self.domain.name,
                file_path=cahier_path,
                analyst_agent_id=self.agent_id,
                content_hash=content_hash
            )

            # Step 6: Create granular tasks from the cahier
            task_ids = await self._create_tasks_from_cahier(cahier_id, tasks_data)

            # Mark agent as completed
            await self.db.update_agent_status(
                self.agent_id,
                AgentStatus.COMPLETED,
                result=f"Cahier created at {cahier_path}, {len(task_ids)} tasks created"
            )

            self.logger.success(
                f"[{self.agent_id}] Cahier created: {cahier_path}, "
                f"{len(task_ids)} tasks generated"
            )

            return {
                "cahier_path": cahier_path,
                "cahier_id": cahier_id,
                "task_ids": task_ids
            }

        except Exception as e:
            self.logger.error(f"[{self.agent_id}] Failed to create cahier: {e}")
            await self.db.update_agent_status(
                self.agent_id,
                AgentStatus.ERROR,
                error_message=str(e)
            )
            return None

    async def _perform_research(self) -> Dict[str, Any]:
        """
        Perform external research using Gemini.

        Returns:
            Research results
        """
        if not self.domain.research_queries:
            return {"results": [], "sources": []}

        all_results = []
        all_sources = set()

        for query in self.domain.research_queries:
            self.logger.info(f"[{self.agent_id}] Researching: {query}")
            result = await self.gemini.research(query, domain=self.domain.name)

            # Store research in database
            cahier_id = f"CAHIER-{self.domain.name}"
            await self.db.create_gemini_research(
                query=query,
                cahier_id=cahier_id,
                results=result
            )

            all_results.append(result)
            if result.get('sources'):
                all_sources.update(result['sources'])

        return {
            "results": all_results,
            "sources": list(all_sources)
        }

    async def _simulate_cahier_generation(self) -> tuple[str, List[Dict[str, Any]]]:
        """
        Simulate cahier generation (placeholder for AI call).

        In production, this would call an AI model with the analyst prompt.

        Returns:
            Tuple of (cahier_content_markdown, tasks_data_list)
        """
        # Simulate processing delay
        await asyncio.sleep(1)

        # Generate task data based on domain
        tasks_data = []

        # Create 2-3 granular tasks per domain
        task_count = 2 if self.domain.complexity in ['trivial', 'simple'] else 3

        for i in range(1, task_count + 1):
            task_data = {
                "title": f"{self.domain.name} - Feature {i}",
                "description": f"Implement feature {i} for {self.domain.name} domain",
                "priority": self.domain.priority,
                "files_scope": [
                    f"src/{self.domain.name.lower()}/feature{i}.js",
                    f"tests/{self.domain.name.lower()}/feature{i}.test.js"
                ],
                "dependencies": []
            }
            tasks_data.append(task_data)

        # Generate template cahier
        cahier = f"""# Cahier des Charges - {self.domain.name}

**Domaine**: {self.domain.name}
**Priorité**: {self.domain.priority}
**Complexité**: {self.domain.complexity}
**Date de création**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 1. Contexte et Analyse

### Besoin Utilisateur
{self.requirement}

### Analyse du Domaine
{self.domain.description}

Ce domaine nécessite une attention particulière avec une priorité **{self.domain.priority}**
et une complexité estimée à **{self.domain.complexity}**.

## 2. Objectifs

- Implémenter les fonctionnalités core du domaine {self.domain.name}
- Assurer l'intégration avec les autres composants du système
- Garantir la sécurité et la performance
- Fournir une documentation complète

## 3. Spécifications Techniques

### Technologies Recommandées

[TODO: Liste des technologies basée sur le domaine]

### Architecture

Architecture basée sur les best practices 2025 pour {self.domain.name}.

[TODO: Diagrammes et descriptions architecturales]

## 4. Fichiers et Structure

```
src/{self.domain.name.lower()}/
├── index.js
├── service.js
├── model.js
├── controller.js
└── tests/
    └── {self.domain.name.lower()}.test.js
```

## 5. Dépendances

### Bibliothèques Externes

[TODO: Liste des bibliothèques npm/pip selon le projet]

### Dépendances Inter-domaines

[TODO: Dépendances identifiées avec d'autres domaines]

## 6. Critères d'Acceptation

- [ ] Toutes les fonctionnalités core implémentées
- [ ] Tests unitaires passent (couverture > 80%)
- [ ] Tests d'intégration passent
- [ ] Documentation à jour
- [ ] Code review approuvé
- [ ] Pas de vulnérabilités de sécurité détectées
- [ ] Performance conforme aux exigences

## 7. Sécurité

### Considérations de Sécurité

- Validation des entrées utilisateur
- Protection contre les injections
- Gestion sécurisée des données sensibles
- Logs d'audit appropriés

### Mesures de Protection

[TODO: Mesures spécifiques au domaine]

## 8. Notes Techniques

### Points d'Attention

- [TODO: Points spécifiques nécessitant attention]

### Contraintes

- [TODO: Contraintes techniques ou business]

### Optimisations Futures

- [TODO: Améliorations potentielles post-MVP]

---

*Ce cahier des charges a été généré par l'agent analyste {self.agent_id}*
*Template utilisé: {self.domain.analyst_template}*
"""

        return cahier, tasks_data

    async def _save_cahier(self, content: str) -> str:
        """
        Save cahier to file.

        Args:
            content: Cahier content in Markdown

        Returns:
            Path to saved file
        """
        # Cahiers are stored in Blueprint directory, not in target project
        blueprint_dir = Path(__file__).parent.parent.parent
        cahiers_dir = blueprint_dir / self.phase0_config.get('cahiers_charges_dir', 'cahiers_charges')
        domain_dir = cahiers_dir / self.domain.name
        domain_dir.mkdir(parents=True, exist_ok=True)

        # Save main cahier for the domain
        cahier_path = domain_dir / "rapport_analyse.md"

        with open(cahier_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return str(cahier_path)

    async def _create_tasks_from_cahier(
        self,
        cahier_id: str,
        tasks_data: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Create granular tasks from the cahier analysis.

        Args:
            cahier_id: ID of the cahier these tasks belong to
            tasks_data: List of task data dictionaries

        Returns:
            List of created task IDs
        """
        task_ids = []
        task_id_start = self.config.get('phase1', {}).get('task_id_start', 101)
        task_id_format = self.config.get('phase1', {}).get('task_id_format', 'TASK-{counter:03d}')

        # Get current max task ID to continue numbering
        try:
            all_tasks = await self.db.get_active_tasks()
            if all_tasks:
                # Extract numeric part from task IDs
                max_num = 0
                for task in all_tasks:
                    tid = task['task_id']
                    if tid.startswith('TASK-'):
                        try:
                            num = int(tid.split('-')[1])
                            max_num = max(max_num, num)
                        except (IndexError, ValueError):
                            pass
                task_counter = max(max_num + 1, task_id_start)
            else:
                task_counter = task_id_start
        except Exception:
            task_counter = task_id_start

        # Cahiers are stored in Blueprint directory, not in target project
        blueprint_dir = Path(__file__).parent.parent.parent
        cahiers_dir = blueprint_dir / self.phase0_config.get('cahiers_charges_dir', 'cahiers_charges')
        domain_dir = cahiers_dir / self.domain.name

        for task_data in tasks_data:
            # Generate task ID
            task_id = task_id_format.format(counter=task_counter)
            task_counter += 1

            # Create a mini spec file for this task
            task_spec_path = domain_dir / f"{task_id}_cahier.md"

            task_spec_content = f"""# {task_data['title']}

**Task ID**: {task_id}
**Domain**: {self.domain.name}
**Priority**: {task_data['priority']}

## Description

{task_data['description']}

## Files Scope

```
{chr(10).join(task_data.get('files_scope', []))}
```

## Dependencies

{', '.join(task_data.get('dependencies', [])) or 'None'}

---

*Ce cahier de tâche est lié au cahier principal: {cahier_id}*
"""

            # Save task-specific cahier
            with open(task_spec_path, 'w', encoding='utf-8') as f:
                f.write(task_spec_content)

            # Create task in database
            await self.db.create_task(
                task_id=task_id,
                domain=self.domain.name,
                title=task_data['title'],
                description=task_data['description'],
                spec_path=str(task_spec_path),
                priority=task_data.get('priority', 'medium'),
                dependencies=task_data.get('dependencies')
            )

            # Link task to cahier in cahiers table
            await self.db.create_cahier(
                cahier_id=f"{cahier_id}-{task_id}",
                domain=self.domain.name,
                task_id=task_id,
                file_path=str(task_spec_path),
                analyst_agent_id=self.agent_id
            )

            # Set task status to CAHIER_READY
            await self.db.update_task_status(task_id, TaskStatus.CAHIER_READY)

            task_ids.append(task_id)

            self.logger.info(f"[{self.agent_id}] Created task {task_id}: {task_data['title']}")

        return task_ids


class MasterAnalyst:
    """
    Phase 0: Master Analyst that creates specialist analyst agents.

    The Master Analyst:
    1. Analyzes the business requirement
    2. Identifies domains needed
    3. Creates analyst agents for each domain
    4. Coordinates cahier generation
    """

    def __init__(
        self,
        config: Dict[str, Any],
        logger: PipelineLogger,
        db: Database,
        agent_factory: AgentFactory
    ):
        """
        Initialize the Master Analyst.

        Args:
            config: Pipeline configuration
            logger: Logger instance
            db: Database instance
            agent_factory: Agent factory for creating specialists
        """
        self.config = config
        self.logger = logger
        self.db = db
        self.factory = agent_factory
        self.phase0_config = config.get('phase0', {})

        # Initialize Gemini researcher if enabled
        self.gemini = None
        if self.phase0_config.get('enable_gemini_research', False):
            self.gemini = GeminiResearcher(
                config=config,
                enabled=True,
                model=self.phase0_config.get('gemini_model', 'gemini-pro')
            )
            self.logger.info("Gemini research enabled")

    def _create_master_prompt(self, requirement: str) -> str:
        """
        Create the prompt for the master analyst.

        Args:
            requirement: High-level business requirement

        Returns:
            Formatted prompt for the master analyst
        """
        max_domains = self.phase0_config.get('max_domains', 10)
        analyst_templates = self.phase0_config.get('analyst_templates', {})

        prompt = f"""# MASTER ANALYST ROLE

You are the Master Analyst in a generative agent pipeline. Your role is to META-ANALYZE
business requirements and create a plan for specialist analyst agents.

## BUSINESS REQUIREMENT

{requirement}

## YOUR TASK

Analyze this requirement and identify specialized domains that need dedicated analyst agents.
Each analyst will create a detailed "cahier des charges" for their domain.

For each domain (max {max_domains}):
1. **Name**: Short domain name (e.g., "Security-DataProtection", "API-Authentication")
2. **Description**: What this domain covers
3. **Analyst Template**: Which agent template should handle this (from available templates)
4. **Priority**: low, medium, high, critical
5. **Complexity**: trivial, simple, moderate, complex, very-complex
6. **Research Queries**: 2-3 specific queries for external research (optional)

## AVAILABLE ANALYST TEMPLATES

{json.dumps(analyst_templates, indent=2)}

## OUTPUT FORMAT

Return ONLY a valid JSON array:

```json
[
  {{
    "name": "Security-DataProtection",
    "description": "Data protection, encryption, and privacy compliance",
    "analyst_template": "security-auditor",
    "priority": "high",
    "complexity": "complex",
    "research_queries": [
      "GDPR compliance best practices 2025",
      "Data encryption standards",
      "PII protection techniques"
    ]
  }}
]
```

## GUIDELINES

- Be specific with domain names (include sub-specialty)
- Each domain should be focused and independent
- Research queries should be specific and actionable
- Balance complexity across domains
- Prioritize based on dependencies

IMPORTANT: Return ONLY the JSON array, no other text.
"""

        return prompt

    async def analyze_and_create_analysts(self, requirement: str) -> List[Domain]:
        """
        Analyze requirement and create analyst agents.

        Args:
            requirement: High-level business requirement

        Returns:
            List of identified domains
        """
        self.logger.phase_start("phase0", "Master Analyst - Creating Analyst Agents")
        self.logger.info(f"Analyzing requirement: {requirement[:100]}...")

        # Create master prompt
        prompt = self._create_master_prompt(requirement)
        self.logger.debug(f"Generated master prompt ({len(prompt)} chars)")

        # TODO: In production, call AI model
        # For now, simulate domain identification
        domains = self._simulate_domain_identification(requirement)

        self.logger.success(f"Identified {len(domains)} domains for analysis")

        for domain in domains:
            self.logger.info(
                f"  → {domain.name} "
                f"(template: {domain.analyst_template}, "
                f"priority: {domain.priority})"
            )

        return domains

    def _simulate_domain_identification(self, requirement: str) -> List[Domain]:
        """
        Simulate domain identification (placeholder).

        Args:
            requirement: Business requirement

        Returns:
            List of identified domains
        """
        requirement_lower = requirement.lower()
        domains = []
        analyst_templates = self.phase0_config.get('analyst_templates', {})

        # Security domain
        if any(word in requirement_lower for word in ['sécurité', 'security', 'protection']):
            domains.append(Domain(
                name="Security",
                description="Analyse de sécurité, protection des données, et prévention des vulnérabilités",
                analyst_template=analyst_templates.get('security', 'security-auditor'),
                priority="high",
                complexity="complex",
                research_queries=[
                    "OWASP Top 10 2025",
                    "Web application security best practices",
                    "Secure coding standards"
                ]
            ))

        # Authentication domain
        if any(word in requirement_lower for word in ['auth', 'login', 'utilisateur', 'jwt']):
            domains.append(Domain(
                name="Authentication",
                description="Système d'authentification et gestion des sessions utilisateur",
                analyst_template=analyst_templates.get('security', 'security-auditor'),
                priority="high",
                complexity="moderate",
                research_queries=[
                    "JWT authentication best practices 2025",
                    "Session management security"
                ]
            ))

        # API domain
        if any(word in requirement_lower for word in ['api', 'endpoint', 'rest']):
            domains.append(Domain(
                name="API",
                description="Conception et implémentation des API REST",
                analyst_template=analyst_templates.get('api', 'senior-engineer'),
                priority="high",
                complexity="moderate",
                research_queries=[
                    "RESTful API design best practices",
                    "API versioning strategies 2025"
                ]
            ))

        # If no specific domains detected
        if not domains:
            domains.append(Domain(
                name="Core",
                description="Fonctionnalités core de l'application",
                analyst_template='senior-engineer',
                priority="high",
                complexity="moderate"
            ))

        return domains

    async def coordinate_analysts(
        self,
        domains: List[Domain],
        requirement: str
    ) -> List[str]:
        """
        Create and coordinate analyst agents to generate cahiers.

        Args:
            domains: List of domains to analyze
            requirement: Original user requirement

        Returns:
            List of paths to generated cahiers
        """
        max_parallel = self.phase0_config.get('max_parallel_analysts', 5)

        self.logger.info(
            f"Creating {len(domains)} analyst agents "
            f"(max {max_parallel} in parallel)..."
        )

        # Create analyst agents
        analysts = [
            AnalystAgent(
                domain=domain,
                requirement=requirement,
                config=self.config,
                logger=self.logger,
                db=self.db,
                agent_factory=self.factory,
                gemini_researcher=self.gemini
            )
            for domain in domains
        ]

        # Run analysts in parallel with semaphore
        semaphore = asyncio.Semaphore(max_parallel)

        async def run_with_semaphore(analyst: AnalystAgent):
            async with semaphore:
                return await analyst.analyze_and_create_cahier()

        # Execute all analysts
        cahier_paths = await asyncio.gather(
            *[run_with_semaphore(analyst) for analyst in analysts]
        )

        # Filter out None values (failed analysts)
        successful_cahiers = [path for path in cahier_paths if path is not None]

        self.logger.success(
            f"Generated {len(successful_cahiers)}/{len(domains)} cahiers successfully"
        )

        return successful_cahiers

    def update_index(self, domains: List[Domain], cahier_paths: List[str]):
        """
        Update the cahiers index file.

        Args:
            domains: List of domains
            cahier_paths: List of generated cahier paths
        """
        # Cahiers are stored in Blueprint directory, not in target project
        blueprint_dir = Path(__file__).parent.parent.parent
        cahiers_dir = blueprint_dir / self.phase0_config.get('cahiers_charges_dir', 'cahiers_charges')
        index_path = cahiers_dir / "index.json"

        # Create mapping
        domain_cahiers = {}
        for domain, path in zip(domains, cahier_paths):
            if path:
                domain_cahiers[domain.name] = {
                    "description": domain.description,
                    "cahier_path": path,
                    "priority": domain.priority,
                    "complexity": domain.complexity,
                    "analyst_template": domain.analyst_template
                }

        # Update index
        index_data = {
            "version": "1.0",
            "description": "Index des cahiers des charges générés par les agents analystes",
            "last_updated": datetime.now().isoformat(),
            "total_domains": len(domain_cahiers),
            "domains": domain_cahiers
        }

        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Updated cahiers index: {index_path}")


async def run_phase0(
    requirement: str,
    config: Dict[str, Any],
    logger: PipelineLogger,
    db: Database
) -> int:
    """
    Execute Phase 0: Master Analyst + Analyst Agents.

    Args:
        requirement: High-level business requirement
        config: Pipeline configuration
        logger: Logger instance
        db: Database instance

    Returns:
        Number of cahiers generated
    """
    if not config.get('phase0', {}).get('enabled', True):
        logger.warning("Phase 0 is disabled in configuration")
        return 0

    factory = AgentFactory(config['agents']['templates_path'])
    master = MasterAnalyst(config, logger, db, factory)

    # Step 1: Analyze requirement and identify domains
    domains = await master.analyze_and_create_analysts(requirement)

    if not domains:
        logger.warning("No domains identified by master analyst")
        return 0

    # Step 2: Create analyst agents and generate cahiers
    cahier_paths = await master.coordinate_analysts(domains, requirement)

    # Step 3: Update index
    master.update_index(domains, cahier_paths)

    logger.phase_end("phase0", success=True)

    return len(cahier_paths)
