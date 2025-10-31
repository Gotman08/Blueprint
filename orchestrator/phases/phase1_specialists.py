"""
Phase 1: Specialist Analysts

Specialist analysts work in parallel, each focusing on their assigned domain.
They create detailed technical specifications (task specs) that will be used
by coder agents in Phase 3.
"""

import asyncio
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
import jsonschema

from orchestrator.agent_factory import AgentFactory
from orchestrator.db import Database, TaskStatus
from orchestrator.utils.logger import PipelineLogger
from orchestrator.phases.phase0_master import Domain


@dataclass
class TaskSpec:
    """Represents a task specification created by a specialist"""
    task_id: str
    created_by: str
    domain: str
    title: str
    description: str
    requirements: List[str]
    files_scope: List[str]
    acceptance_criteria: List[str]
    dependencies: List[str]
    priority: str
    estimated_complexity: str
    tags: List[str]
    technical_notes: Optional[str] = None


class SpecialistAnalyst:
    """A specialist analyst focused on a specific domain"""

    def __init__(
        self,
        domain: Domain,
        config: Dict[str, Any],
        logger: PipelineLogger,
        factory: AgentFactory,
        db: Database,
        task_id_counter: int
    ):
        """
        Initialize specialist analyst.

        Args:
            domain: Domain this analyst is specialized in
            config: Pipeline configuration
            logger: Logger instance
            factory: Agent factory
            db: Database instance
            task_id_counter: Starting counter for task IDs
        """
        self.domain = domain
        self.config = config
        self.logger = logger
        self.factory = factory
        self.db = db
        self.task_id_counter = task_id_counter

        self.agent_id = f"Analyst-{domain.name}"
        self.specs_dir = Path(config['specs']['directory'])
        self.specs_dir.mkdir(parents=True, exist_ok=True)

    def _generate_task_id(self) -> str:
        """Generate next task ID"""
        task_format = self.config['phase1'].get('task_id_format', 'TASK-{counter:03d}')
        task_id = task_format.format(counter=self.task_id_counter)
        self.task_id_counter += 1
        return task_id

    def _create_specialist_prompt(self) -> str:
        """Create prompt for this specialist analyst"""
        return f"""# SPECIALIST ANALYST - {self.domain.name.upper()}

You are a specialist analyst for the **{self.domain.name}** domain.

## DOMAIN SCOPE

{self.domain.description}

**Priority**: {self.domain.priority}
**Complexity**: {self.domain.complexity}

## YOUR TASK

Create detailed technical specifications for implementing this domain.

Break down this domain into individual, actionable tasks. For EACH task, provide:

1. **Title**: Clear, concise feature title
2. **Description**: Detailed description of what needs to be implemented
3. **Requirements**: List of specific technical requirements (minimum 2)
4. **Files Scope**: Directories or files to create/modify (e.g., ["src/auth/", "tests/auth/"])
5. **Acceptance Criteria**: Testable criteria for completion (minimum 2)
6. **Dependencies**: Task IDs this depends on (empty array if none)
7. **Priority**: low, medium, high, critical
8. **Estimated Complexity**: trivial, simple, moderate, complex, very-complex
9. **Tags**: Categorization tags (e.g., ["security", "api"])
10. **Technical Notes**: Additional constraints or considerations (optional)

## GUIDELINES

- Create 2-5 tasks for this domain
- Each task should be focused and implementable independently
- Be specific about file paths and technical requirements
- Include security and performance considerations
- Ensure acceptance criteria are testable
- Break complex features into smaller tasks

## OUTPUT

Return a JSON array of task specifications. Each task must follow this structure:

```json
[
  {{
    "title": "Implement JWT token generation",
    "description": "Create a service that generates JWT tokens with user ID and roles",
    "requirements": [
      "Use jsonwebtoken library",
      "Token expiry: 24 hours",
      "Include user ID and roles in payload"
    ],
    "files_scope": [
      "src/auth/jwt-service.js",
      "src/config/jwt.js"
    ],
    "acceptance_criteria": [
      "Token generation function exists and is exported",
      "Generated tokens are valid JWT format",
      "Tokens contain correct user data"
    ],
    "dependencies": [],
    "priority": "high",
    "estimated_complexity": "moderate",
    "tags": ["security", "authentication"],
    "technical_notes": "Ensure secret is loaded from environment variables"
  }}
]
```
"""

    async def analyze(self) -> List[TaskSpec]:
        """
        Analyze the domain and create task specifications.

        Returns:
            List of task specifications
        """
        self.logger.agent_created(self.agent_id, "specialist-analyst", self.domain.name)
        self.logger.agent_working(self.agent_id, f"Analyzing {self.domain.name} domain")

        # Create specialist prompt
        prompt = self._create_specialist_prompt()

        # TODO: In production, invoke AI model with this prompt
        # For now, simulate with domain-specific tasks
        raw_tasks = self._simulate_analysis()

        # Convert to TaskSpec objects with generated IDs
        specs = []
        for task_data in raw_tasks:
            task_id = self._generate_task_id()

            spec = TaskSpec(
                task_id=task_id,
                created_by=self.agent_id,
                domain=self.domain.name,
                title=task_data['title'],
                description=task_data['description'],
                requirements=task_data['requirements'],
                files_scope=task_data.get('files_scope', []),
                acceptance_criteria=task_data['acceptance_criteria'],
                dependencies=task_data.get('dependencies', []),
                priority=task_data.get('priority', self.domain.priority),
                estimated_complexity=task_data.get('estimated_complexity', self.domain.complexity),
                tags=task_data.get('tags', []),
                technical_notes=task_data.get('technical_notes')
            )

            specs.append(spec)

        self.logger.agent_completed(self.agent_id)
        self.logger.success(f"Created {len(specs)} task specifications for {self.domain.name}")

        return specs

    def _simulate_analysis(self) -> List[Dict[str, Any]]:
        """
        Simulate domain analysis (temporary implementation).

        Returns:
            List of simulated task data
        """
        # Domain-specific task templates
        domain_tasks = {
            "Authentication": [
                {
                    "title": "Implement JWT token generation",
                    "description": "Create a service that generates JWT tokens with user ID, roles, and expiration",
                    "requirements": [
                        "Use jsonwebtoken library",
                        "Token expiry: 24 hours",
                        "Include user ID and roles in payload",
                        "Secret must be loaded from environment variables"
                    ],
                    "files_scope": ["src/auth/jwt-service.js", "src/config/jwt.js"],
                    "acceptance_criteria": [
                        "Token generation function exists and is exported",
                        "Generated tokens are valid JWT format",
                        "Tokens contain correct user data and expiry"
                    ],
                    "priority": "high",
                    "estimated_complexity": "moderate",
                    "tags": ["security", "authentication", "jwt"]
                },
                {
                    "title": "Create authentication middleware",
                    "description": "Implement Express middleware to verify JWT tokens on protected routes",
                    "requirements": [
                        "Verify token signature",
                        "Check token expiration",
                        "Attach user data to request object",
                        "Return 401 for invalid tokens"
                    ],
                    "files_scope": ["src/middleware/auth.js", "tests/middleware/auth.test.js"],
                    "acceptance_criteria": [
                        "Middleware rejects requests without tokens",
                        "Middleware rejects expired tokens",
                        "Middleware attaches user data for valid tokens"
                    ],
                    "priority": "high",
                    "estimated_complexity": "simple",
                    "tags": ["security", "middleware"]
                }
            ],
            "API": [
                {
                    "title": "Design REST API structure",
                    "description": "Define RESTful API endpoints with proper HTTP methods and status codes",
                    "requirements": [
                        "Follow REST conventions",
                        "Use proper HTTP status codes",
                        "Implement versioning (v1)",
                        "Document all endpoints"
                    ],
                    "files_scope": ["docs/api-spec.md", "src/routes/"],
                    "acceptance_criteria": [
                        "API specification document exists",
                        "All endpoints follow RESTful conventions",
                        "Proper status codes are used"
                    ],
                    "priority": "high",
                    "estimated_complexity": "moderate",
                    "tags": ["api", "design", "documentation"]
                }
            ],
            "Database": [
                {
                    "title": "Design database schema",
                    "description": "Create database schema with tables, relationships, and indexes",
                    "requirements": [
                        "Use PostgreSQL",
                        "Include proper foreign keys",
                        "Add indexes for performance",
                        "Support migrations"
                    ],
                    "files_scope": ["db/migrations/", "db/schema.sql"],
                    "acceptance_criteria": [
                        "Schema file exists with all tables",
                        "Foreign key relationships are defined",
                        "Indexes are created for frequently queried fields"
                    ],
                    "priority": "critical",
                    "estimated_complexity": "complex",
                    "tags": ["database", "schema", "postgresql"]
                }
            ],
            "Frontend": [
                {
                    "title": "Create component library structure",
                    "description": "Set up component library with reusable UI components",
                    "requirements": [
                        "Use React functional components",
                        "Implement with TypeScript",
                        "Use CSS modules for styling",
                        "Include Storybook documentation"
                    ],
                    "files_scope": ["src/components/", "src/components/index.ts"],
                    "acceptance_criteria": [
                        "Component library structure exists",
                        "At least 3 base components are implemented",
                        "Components are properly typed with TypeScript"
                    ],
                    "priority": "medium",
                    "estimated_complexity": "moderate",
                    "tags": ["frontend", "react", "components"]
                }
            ],
            "Payments": [
                {
                    "title": "Integrate Stripe payment processing",
                    "description": "Implement Stripe integration for payment processing",
                    "requirements": [
                        "Use Stripe SDK",
                        "Handle payment intents",
                        "Implement webhook for payment confirmation",
                        "Store payment records in database"
                    ],
                    "files_scope": ["src/payments/stripe-service.js", "src/routes/payments.js"],
                    "acceptance_criteria": [
                        "Payments can be processed successfully",
                        "Webhook handles payment confirmations",
                        "Payment records are stored correctly"
                    ],
                    "priority": "critical",
                    "estimated_complexity": "very-complex",
                    "tags": ["payments", "stripe", "integration"]
                }
            ]
        }

        # Return domain-specific tasks or generic fallback
        return domain_tasks.get(
            self.domain.name,
            [
                {
                    "title": f"Implement core {self.domain.name} functionality",
                    "description": f"Create the main functionality for {self.domain.name}",
                    "requirements": [
                        "Follow project coding standards",
                        "Include error handling",
                        "Add logging"
                    ],
                    "files_scope": [f"src/{self.domain.name.lower()}/"],
                    "acceptance_criteria": [
                        "Core functionality is implemented",
                        "Error handling is in place",
                        "Code passes linting"
                    ],
                    "priority": self.domain.priority,
                    "estimated_complexity": self.domain.complexity,
                    "tags": [self.domain.name.lower()]
                }
            ]
        )

    async def save_specs(self, specs: List[TaskSpec]) -> List[str]:
        """
        Save task specifications to files and database.

        Args:
            specs: List of task specifications

        Returns:
            List of file paths where specs were saved
        """
        saved_files = []

        # Load schema for validation
        schema_path = Path(self.config['specs']['schema_path'])
        with open(schema_path) as f:
            schema = json.load(f)

        for spec in specs:
            # Convert to dict
            spec_dict = {
                "task_id": spec.task_id,
                "created_by": spec.created_by,
                "domain": spec.domain,
                "title": spec.title,
                "description": spec.description,
                "requirements": spec.requirements,
                "files_scope": spec.files_scope,
                "acceptance_criteria": spec.acceptance_criteria,
                "dependencies": spec.dependencies,
                "priority": spec.priority,
                "estimated_complexity": spec.estimated_complexity,
                "tags": spec.tags,
                "metadata": {
                    "created_at": datetime.now().isoformat(),
                    "analyst_version": "1.0",
                    "spec_version": "1.0"
                }
            }

            if spec.technical_notes:
                spec_dict["technical_notes"] = spec.technical_notes

            # Validate against schema
            if self.config['specs'].get('validate', True):
                try:
                    jsonschema.validate(spec_dict, schema)
                except jsonschema.ValidationError as e:
                    self.logger.error(f"Spec validation failed for {spec.task_id}: {e.message}")
                    continue

            # Save to file
            spec_file = self.specs_dir / f"{spec.task_id}.json"
            with open(spec_file, 'w', encoding='utf-8') as f:
                json.dump(spec_dict, f, indent=2, ensure_ascii=False)

            saved_files.append(str(spec_file))

            # Save to database
            await self.db.create_task(
                task_id=spec.task_id,
                domain=spec.domain,
                title=spec.title,
                description=spec.description,
                spec_path=str(spec_file),
                priority=spec.priority,
                dependencies=spec.dependencies if spec.dependencies else None
            )

            self.logger.info(f"  ✓ Saved {spec.task_id}: {spec.title}")

        return saved_files


async def run_phase1(
    domains: List[Domain],
    config: Dict[str, Any],
    logger: PipelineLogger,
    db: Database
) -> int:
    """
    Execute Phase 1: Specialist Analysts (parallel execution).

    Args:
        domains: List of domains from Phase 0
        config: Pipeline configuration
        logger: Logger instance
        db: Database instance

    Returns:
        Total number of task specs created
    """
    logger.phase_start("phase1", "Specialist Analysts - Specification Generation")

    factory = AgentFactory(config['agents']['templates_path'])
    phase1_config = config.get('phase1', {})

    # Task ID counter
    task_id_start = phase1_config.get('task_id_start', 101)
    task_id_counter = task_id_start

    # Create specialist analysts
    specialists = []
    for domain in domains:
        specialist = SpecialistAnalyst(
            domain=domain,
            config=config,
            logger=logger,
            factory=factory,
            db=db,
            task_id_counter=task_id_counter
        )
        specialists.append(specialist)

        # Update counter (rough estimate, will be adjusted)
        task_id_counter += 10  # Reserve 10 IDs per domain

    # Run analysts in parallel
    max_parallel = phase1_config.get('max_parallel_agents', 5)

    logger.info(f"Running {len(specialists)} specialist analysts (max {max_parallel} parallel)")

    # Execute in parallel with semaphore for concurrency control
    semaphore = asyncio.Semaphore(max_parallel)

    async def analyze_and_save(specialist):
        async with semaphore:
            specs = await specialist.analyze()
            await specialist.save_specs(specs)
            return len(specs)

    results = await asyncio.gather(*[analyze_and_save(s) for s in specialists])

    total_specs = sum(results)

    logger.success(f"Phase 1 complete: {total_specs} task specifications created")
    logger.phase_end("phase1", success=True)

    return total_specs
