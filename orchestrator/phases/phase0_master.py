"""
Phase 0: Master Analyst

The Master Analyst receives a high-level business requirement and breaks it down
into specialized domains, creating specialist analyst agents for each domain.

This is the "generator" that starts the entire pipeline.
"""

import asyncio
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass

from orchestrator.agent_factory import AgentFactory
from orchestrator.utils.logger import PipelineLogger


@dataclass
class Domain:
    """Represents a domain identified by the master analyst"""
    name: str
    description: str
    template: str
    priority: str = "medium"
    complexity: str = "moderate"


class MasterAnalyst:
    """
    Phase 0: Analyzes business requirements and identifies domains.

    The Master Analyst doesn't analyze requirements directly - it analyzes
    how requirements should be analyzed, then creates specialist agents.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        logger: PipelineLogger,
        agent_factory: AgentFactory
    ):
        """
        Initialize the Master Analyst.

        Args:
            config: Pipeline configuration
            logger: Logger instance
            agent_factory: Agent factory for creating specialists
        """
        self.config = config
        self.logger = logger
        self.factory = agent_factory
        self.phase0_config = config.get('phase0', {})

    def _create_master_prompt(self, requirement: str) -> str:
        """
        Create the prompt for the master analyst.

        Args:
            requirement: High-level business requirement

        Returns:
            Formatted prompt for the master analyst
        """
        max_domains = self.phase0_config.get('max_domains', 10)
        min_domains = self.phase0_config.get('min_domains', 1)
        domain_templates = self.phase0_config.get('domain_templates', {})

        prompt = f"""# MASTER ANALYST ROLE

You are the Master Analyst in a generative agent pipeline. Your role is NOT to analyze
the business requirement directly, but to META-ANALYZE it:

**Your job is to determine HOW this requirement should be analyzed.**

## BUSINESS REQUIREMENT

{requirement}

## YOUR TASK

Analyze this requirement and identify {min_domains}-{max_domains} specialized domains that need dedicated analyst agents.

For each domain:
1. **Name**: Short domain name (e.g., "Authentication", "Payments", "Database")
2. **Description**: What this domain covers
3. **Template**: Which agent template should handle this domain (choose from available templates)
4. **Priority**: low, medium, high, critical
5. **Complexity**: trivial, simple, moderate, complex, very-complex

## AVAILABLE DOMAIN TEMPLATES

The following specialist templates are available:
{json.dumps(domain_templates, indent=2)}

## OUTPUT FORMAT

Return ONLY a valid JSON array with this structure:

```json
[
  {{
    "name": "Authentication",
    "description": "User authentication and JWT token management",
    "template": "security-auditor",
    "priority": "high",
    "complexity": "moderate"
  }},
  {{
    "name": "Payments",
    "description": "Payment processing with Stripe integration",
    "template": "senior-engineer",
    "priority": "critical",
    "complexity": "complex"
  }}
]
```

## GUIDELINES

- Each domain should be independent and focused
- Domains should cover ALL aspects of the requirement
- Choose templates that best match each domain's nature
- Balance complexity across domains (don't make everything "very-complex")
- Prioritize based on dependencies (what needs to be built first)

IMPORTANT: Return ONLY the JSON array, no other text.
"""

        return prompt

    async def analyze_requirement(self, requirement: str) -> List[Domain]:
        """
        Analyze a business requirement and identify domains.

        This is a simulation - in production, this would call an AI model.

        Args:
            requirement: High-level business requirement

        Returns:
            List of identified domains
        """
        self.logger.phase_start("phase0", "Master Analyst - Requirement Analysis")
        self.logger.info(f"Analyzing requirement: {requirement[:100]}...")

        # Create master analyst prompt
        prompt = self._create_master_prompt(requirement)

        self.logger.info("Generated master analyst prompt")
        self.logger.debug(f"Prompt length: {len(prompt)} characters")

        # TODO: In production, this would invoke an AI model (Claude Opus)
        # For now, we'll simulate with a basic domain extraction
        domains = self._simulate_analysis(requirement)

        self.logger.success(f"Identified {len(domains)} domains")

        for domain in domains:
            self.logger.info(
                f"  → {domain.name} "
                f"(template: {domain.template}, "
                f"priority: {domain.priority}, "
                f"complexity: {domain.complexity})"
            )

        self.logger.phase_end("phase0", success=True)

        return domains

    def _simulate_analysis(self, requirement: str) -> List[Domain]:
        """
        Simulate domain analysis (temporary implementation).

        In production, this would be replaced with actual AI model calls.

        Args:
            requirement: Business requirement

        Returns:
            List of simulated domains
        """
        # Keyword-based domain detection for simulation
        requirement_lower = requirement.lower()

        domains = []
        domain_templates = self.phase0_config.get('domain_templates', {})

        # Authentication/Security
        if any(word in requirement_lower for word in ['auth', 'login', 'user', 'security', 'jwt']):
            domains.append(Domain(
                name="Authentication",
                description="User authentication and authorization system",
                template=domain_templates.get('authentication', 'security-auditor'),
                priority="high",
                complexity="moderate"
            ))

        # API
        if any(word in requirement_lower for word in ['api', 'endpoint', 'rest', 'graphql']):
            domains.append(Domain(
                name="API",
                description="API design and implementation",
                template=domain_templates.get('api', 'api-designer'),
                priority="high",
                complexity="moderate"
            ))

        # Database
        if any(word in requirement_lower for word in ['database', 'data', 'storage', 'sql', 'nosql']):
            domains.append(Domain(
                name="Database",
                description="Database schema and data management",
                template=domain_templates.get('database', 'database-specialist'),
                priority="critical",
                complexity="moderate"
            ))

        # Frontend
        if any(word in requirement_lower for word in ['ui', 'frontend', 'interface', 'react', 'vue']):
            domains.append(Domain(
                name="Frontend",
                description="User interface and frontend components",
                template=domain_templates.get('frontend', 'ui-ux-designer'),
                priority="medium",
                complexity="complex"
            ))

        # Backend
        if any(word in requirement_lower for word in ['backend', 'server', 'service', 'business logic']):
            domains.append(Domain(
                name="Backend",
                description="Backend services and business logic",
                template=domain_templates.get('backend', 'senior-engineer'),
                priority="high",
                complexity="complex"
            ))

        # Payments
        if any(word in requirement_lower for word in ['payment', 'stripe', 'billing', 'checkout']):
            domains.append(Domain(
                name="Payments",
                description="Payment processing and billing",
                template=domain_templates.get('backend', 'senior-engineer'),
                priority="critical",
                complexity="very-complex"
            ))

        # Testing
        if any(word in requirement_lower for word in ['test', 'testing', 'qa']):
            domains.append(Domain(
                name="Testing",
                description="Test infrastructure and test cases",
                template=domain_templates.get('testing', 'test-automation'),
                priority="medium",
                complexity="moderate"
            ))

        # DevOps/Infrastructure
        if any(word in requirement_lower for word in ['deploy', 'infrastructure', 'docker', 'ci/cd']):
            domains.append(Domain(
                name="DevOps",
                description="Deployment and infrastructure setup",
                template=domain_templates.get('devops', 'devops-engineer'),
                priority="medium",
                complexity="complex"
            ))

        # If no specific domains detected, create a generic one
        if not domains:
            domains.append(Domain(
                name="Core",
                description="Core application functionality",
                template='senior-engineer',
                priority="high",
                complexity="moderate"
            ))

        return domains

    def generate_specialist_prompts(self, domains: List[Domain]) -> Dict[str, str]:
        """
        Generate prompts for specialist analyst agents.

        Args:
            domains: List of identified domains

        Returns:
            Dictionary mapping domain names to specialist prompts
        """
        prompts = {}

        for domain in domains:
            prompt = f"""# SPECIALIST ANALYST - {domain.name.upper()}

You are a specialist analyst for the **{domain.name}** domain.

## DOMAIN SCOPE

{domain.description}

**Priority**: {domain.priority}
**Complexity**: {domain.complexity}

## YOUR TASK

Create detailed technical specifications for implementing this domain.

For EACH feature or component in this domain, create a separate task specification with:

1. **Task ID**: Use format TASK-XXX (will be assigned by system)
2. **Title**: Clear, concise feature title
3. **Description**: Detailed description of what needs to be implemented
4. **Requirements**: List of specific technical requirements
5. **Files Scope**: Directories or files that should be created/modified
6. **Acceptance Criteria**: Testable criteria for completion
7. **Dependencies**: Other task IDs this depends on (if any)
8. **Priority**: low, medium, high, critical
9. **Technical Notes**: Any additional constraints or considerations

## OUTPUT FORMAT

Generate a JSON array of task specifications following the schema in config/spec_schema.json.

Each task should be:
- **Focused**: One clear objective
- **Testable**: Clear acceptance criteria
- **Independent**: Minimize dependencies where possible
- **Detailed**: Enough information for a coder to implement without questions

## GUIDELINES

- Break complex features into smaller tasks
- Ensure tasks can be worked on in parallel where possible
- Be specific about file paths and technical requirements
- Include security and performance considerations
- Don't forget error handling and edge cases

Remember: Your specifications will be the "contract" that coder agents must fulfill.
Be precise and thorough.
"""

            prompts[domain.name] = prompt

        return prompts

    def save_domain_analysis(
        self,
        domains: List[Domain],
        output_path: Optional[str] = None
    ) -> str:
        """
        Save domain analysis results to file.

        Args:
            domains: List of identified domains
            output_path: Optional custom output path

        Returns:
            Path to saved file
        """
        if output_path is None:
            output_path = "specs/domain_analysis.json"

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "total_domains": len(domains),
            "domains": [
                {
                    "name": d.name,
                    "description": d.description,
                    "template": d.template,
                    "priority": d.priority,
                    "complexity": d.complexity
                }
                for d in domains
            ]
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Saved domain analysis to {output_file}")

        return str(output_file)


async def run_phase0(
    requirement: str,
    config: Dict[str, Any],
    logger: PipelineLogger
) -> List[Domain]:
    """
    Execute Phase 0: Master Analyst.

    Args:
        requirement: High-level business requirement
        config: Pipeline configuration
        logger: Logger instance

    Returns:
        List of identified domains for Phase 1
    """
    factory = AgentFactory(config['agents']['templates_path'])
    master = MasterAnalyst(config, logger, factory)

    # Analyze requirement and identify domains
    domains = await master.analyze_requirement(requirement)

    # Save domain analysis
    master.save_domain_analysis(domains)

    return domains
