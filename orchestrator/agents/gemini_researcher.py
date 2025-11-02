"""
Gemini Researcher Agent - External research for cahiers des charges enrichment.

This agent performs web searches and documentation research to provide
additional context and best practices for analyst agents.
Uses Gemini CLI for research instead of direct API calls.
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime


# Research prompt templates
RESEARCH_PROMPTS = {
    "general": """
Research the following topic: {query}
{domain_context}
{task_context}

Provide a comprehensive response including:
- Key findings and insights
- Best practices and recommendations
- Relevant standards or frameworks
- Common pitfalls to avoid
- Recent developments (2024-2025)

Format your response as JSON with the following structure:
{{
    "findings": [
        {{
            "title": "Finding title",
            "summary": "Detailed summary",
            "relevance": "high/medium/low"
        }}
    ],
    "sources": ["List of relevant sources or documentation"],
    "recommendations": ["Key recommendations"],
    "warnings": ["Important warnings or pitfalls"]
}}
    """,

    "best_practices": """
Research current best practices for {domain} in 2025.
{tech_stack_context}

Focus on:
- Architecture patterns and design principles
- Security considerations
- Performance optimization strategies
- Testing approaches
- Monitoring and observability
- Common anti-patterns to avoid

Format your response as JSON with:
{{
    "findings": [
        {{
            "title": "Practice name",
            "summary": "Detailed description",
            "relevance": "high/medium/low"
        }}
    ],
    "sources": ["Documentation and reference links"],
    "implementation_tips": ["Practical implementation advice"]
}}
    """,

    "security": """
Analyze security considerations for {vulnerability_type}.

Include:
- OWASP Top 10 2025 relevance
- Common attack vectors
- Mitigation strategies with code examples
- Security testing approaches
- Defense in depth strategies
- Compliance requirements (GDPR, SOC2, etc.)

Format your response as JSON:
{{
    "findings": [
        {{
            "title": "Security aspect",
            "summary": "Detailed explanation",
            "relevance": "high/medium/low"
        }}
    ],
    "sources": ["Security references and standards"],
    "mitigations": ["Specific mitigation strategies"],
    "testing_approaches": ["How to test for this vulnerability"]
}}
    """,

    "documentation": """
Find comprehensive documentation for {library} library/framework.
{use_case_context}

Focus on:
- Latest stable version features (2025)
- Installation and setup
- Core API and methods
- Code examples for common use cases
- Integration patterns
- Performance considerations
- Migration guides if applicable

Format as JSON:
{{
    "findings": [
        {{
            "title": "Documentation section",
            "summary": "Key information",
            "relevance": "high/medium/low"
        }}
    ],
    "sources": ["Official documentation links"],
    "code_examples": ["Practical code snippets"],
    "version_info": "Latest stable version details"
}}
    """
}


class GeminiResearcher:
    """
    Research agent using Gemini CLI for external documentation and best practices.

    This agent is optional and can be enabled/disabled via configuration.
    When enabled, it enriches cahiers des charges with:
    - Current best practices
    - Documentation references
    - Security recommendations
    - Implementation examples
    """

    def __init__(
        self,
        config: Dict[str, Any],
        enabled: bool = True,
        model: str = None
    ):
        """
        Initialize the Gemini Researcher.

        Args:
            config: Pipeline configuration dictionary
            enabled: Whether research is enabled
            model: Gemini model to use (default from config or "gemini-2.5-pro")
        """
        self.config = config
        gemini_config = config.get('gemini', {})

        # Check if CLI mode is enabled
        self.use_cli = gemini_config.get('use_cli', True)
        self.enabled = enabled and self.use_cli

        # CLI configuration
        self.model = model or gemini_config.get('cli_model', 'gemini-2.5-pro')
        self.timeout = gemini_config.get('cli_timeout', 30)
        self.max_retries = gemini_config.get('max_retries', 2)

        # Optional caching
        self.cache_enabled = gemini_config.get('cache_results', False)
        self.cache = {} if self.cache_enabled else None

        # Setup logging
        self.logger = logging.getLogger(__name__)

        # CLI command (will be set by _check_gemini_cli_available)
        self.cli_command = None

        # Check CLI availability on init
        if self.enabled:
            asyncio.create_task(self._verify_cli_availability())

    async def _verify_cli_availability(self):
        """Verify that Gemini CLI is available and configured."""
        if not await self._check_gemini_cli_available():
            self.logger.warning(
                "Gemini CLI not found or not configured. "
                "Please install with: npm install -g @google/gemini-cli "
                "and authenticate with: gemini auth login"
            )
            self.enabled = False

    async def _check_gemini_cli_available(self) -> bool:
        """
        Check if Gemini CLI is installed and available.
        Tries both direct execution and npx.

        Returns:
            True if Gemini CLI is available, False otherwise
        """
        # First try direct gemini command
        try:
            process = await asyncio.create_subprocess_exec(
                "gemini", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                version = stdout.decode().strip()
                self.logger.info(f"Gemini CLI found (direct): {version}")
                self.cli_command = ["gemini"]
                return True
        except FileNotFoundError:
            pass  # Try npx next
        except Exception as e:
            self.logger.debug(f"Direct gemini check failed: {e}")

        # Try with npx (using npx.cmd on Windows)
        try:
            # On Windows, use npx.cmd
            import platform
            npx_cmd = "npx.cmd" if platform.system() == "Windows" else "npx"

            process = await asyncio.create_subprocess_exec(
                npx_cmd, "@google/gemini-cli", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                # Extract version from output
                output = stdout.decode().strip()
                # Version might be on first or last line depending on npx output
                lines = output.split('\n')
                version = lines[-1] if lines else "unknown"
                self.logger.info(f"Gemini CLI found (npx): {version}")
                self.cli_command = [npx_cmd, "@google/gemini-cli"]
                return True
            else:
                self.logger.error(f"Gemini CLI npx error: {stderr.decode()}")
                return False

        except FileNotFoundError:
            self.logger.error("Neither gemini nor npx found in PATH")
            return False
        except Exception as e:
            self.logger.error(f"Error checking Gemini CLI: {e}")
            return False

    async def _call_gemini_cli(
        self,
        prompt: str,
        output_format: str = "json"
    ) -> Dict[str, Any]:
        """
        Execute a Gemini CLI command with the given prompt.

        Args:
            prompt: The prompt to send to Gemini
            output_format: Output format (json, text, or stream-json)

        Returns:
            Parsed response from Gemini CLI

        Raises:
            TimeoutError: If the command times out
            RuntimeError: If the command fails
        """
        # Ensure CLI command is set
        if not self.cli_command:
            raise RuntimeError("Gemini CLI command not initialized. CLI might not be available.")

        # Build command
        cmd = self.cli_command + [prompt]

        if output_format:
            cmd.extend(["--output-format", output_format])

        if self.model:
            cmd.extend(["--model", self.model])

        self.logger.debug(f"Executing Gemini CLI: {' '.join(cmd[:len(self.cli_command)+1])}...")  # Log without full prompt

        try:
            # Create subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Wait with timeout
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout
            )

            if process.returncode != 0:
                error_msg = stderr.decode().strip()
                raise RuntimeError(f"Gemini CLI failed: {error_msg}")

            # Parse response based on format
            response_text = stdout.decode().strip()

            if output_format == "json":
                try:
                    return json.loads(response_text)
                except json.JSONDecodeError as e:
                    self.logger.error(f"Failed to parse JSON response: {e}")
                    # Return as text if JSON parsing fails
                    return {"text": response_text}
            else:
                return {"text": response_text}

        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()  # Clean up
            raise TimeoutError(f"Gemini CLI timeout after {self.timeout} seconds")
        except Exception as e:
            self.logger.error(f"Gemini CLI error: {e}")
            raise

    async def research(
        self,
        query: str,
        domain: Optional[str] = None,
        task_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Perform research on a specific topic.

        Args:
            query: Research query
            domain: Optional domain context (e.g., "Security", "API")
            task_context: Optional task context for more specific research

        Returns:
            Dict containing:
                - query: Original query
                - domain: Domain context
                - results: List of research findings
                - sources: List of source URLs/references
                - timestamp: When research was performed
                - model: Model used
        """
        if not self.enabled:
            return self._empty_response(query, domain, message="Gemini research is disabled")

        # Check cache if enabled
        cache_key = f"{query}:{domain}:{str(task_context)}" if self.cache_enabled else None
        if cache_key and cache_key in self.cache:
            self.logger.info(f"Returning cached research for: {query}")
            return self.cache[cache_key]

        try:
            # Build research prompt
            prompt = self._build_research_prompt(query, domain, task_context)

            # Call Gemini CLI with retries
            response = None
            for attempt in range(self.max_retries):
                try:
                    response = await self._call_gemini_cli(prompt)
                    break
                except (TimeoutError, RuntimeError) as e:
                    if attempt < self.max_retries - 1:
                        self.logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying...")
                        await asyncio.sleep(2)  # Brief pause before retry
                    else:
                        raise

            # Parse and format response
            results = self._parse_gemini_response(response, query, domain)

            # Cache if enabled
            if cache_key:
                self.cache[cache_key] = results

            return results

        except Exception as e:
            self.logger.error(f"Research failed for '{query}': {e}")
            return self._empty_response(query, domain, error=str(e))

    async def research_best_practices(
        self,
        domain: str,
        technology_stack: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Research best practices for a specific domain.

        Args:
            domain: Domain name (e.g., "Security", "Authentication")
            technology_stack: Optional list of technologies (e.g., ["Node.js", "JWT"])

        Returns:
            Research results with best practices
        """
        # Build context from technology stack
        tech_context = ""
        if technology_stack:
            tech_context = f"Technology stack: {', '.join(technology_stack)}"

        # Use best practices template
        prompt = RESEARCH_PROMPTS["best_practices"].format(
            domain=domain,
            tech_stack_context=tech_context
        )

        # Execute research
        return await self._research_with_template(prompt, domain=domain)

    async def research_security_recommendations(
        self,
        vulnerability_type: str
    ) -> Dict[str, Any]:
        """
        Research security recommendations for specific vulnerability types.

        Args:
            vulnerability_type: Type of vulnerability (e.g., "SQL Injection", "XSS")

        Returns:
            Security recommendations and mitigations
        """
        prompt = RESEARCH_PROMPTS["security"].format(
            vulnerability_type=vulnerability_type
        )

        return await self._research_with_template(prompt, domain="Security")

    async def research_library_documentation(
        self,
        library_name: str,
        use_case: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Research documentation for a specific library or framework.

        Args:
            library_name: Name of the library/framework
            use_case: Optional specific use case

        Returns:
            Documentation and usage examples
        """
        use_case_context = f"Specific use case: {use_case}" if use_case else ""

        prompt = RESEARCH_PROMPTS["documentation"].format(
            library=library_name,
            use_case_context=use_case_context
        )

        return await self._research_with_template(prompt, domain="Documentation")

    async def batch_research(
        self,
        queries: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Perform multiple research queries in parallel.

        Args:
            queries: List of query dicts with 'query', 'domain', and optional 'task_context'

        Returns:
            List of research results
        """
        tasks = []
        for query_info in queries:
            task = self.research(
                query=query_info['query'],
                domain=query_info.get('domain'),
                task_context=query_info.get('task_context')
            )
            tasks.append(task)

        return await asyncio.gather(*tasks)

    def is_enabled(self) -> bool:
        """Check if Gemini research is enabled."""
        return self.enabled

    def _build_research_prompt(
        self,
        query: str,
        domain: Optional[str] = None,
        task_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Build a comprehensive research prompt.

        Args:
            query: Base query
            domain: Optional domain
            task_context: Optional task context

        Returns:
            Formatted prompt string
        """
        # Add domain context if provided
        domain_context = f"Domain: {domain}" if domain else ""

        # Add task context if provided
        task_context_str = ""
        if task_context:
            task_context_str = "Task context:\n"
            for key, value in task_context.items():
                task_context_str += f"- {key}: {value}\n"

        # Use general template
        prompt = RESEARCH_PROMPTS["general"].format(
            query=query,
            domain_context=domain_context,
            task_context=task_context_str
        )

        return prompt.strip()

    async def _research_with_template(
        self,
        prompt: str,
        domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute research with a specific template prompt.

        Args:
            prompt: Pre-formatted prompt from template
            domain: Optional domain for metadata

        Returns:
            Research results
        """
        if not self.enabled:
            return self._empty_response("", domain)

        try:
            response = await self._call_gemini_cli(prompt)
            return self._parse_gemini_response(response, prompt[:50] + "...", domain)
        except Exception as e:
            self.logger.error(f"Template research failed: {e}")
            return self._empty_response("", domain, error=str(e))

    def _parse_gemini_response(
        self,
        response: Dict[str, Any],
        query: str,
        domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Parse Gemini CLI response into expected format.

        Args:
            response: Raw response from Gemini CLI
            query: Original query
            domain: Optional domain

        Returns:
            Formatted research results
        """
        timestamp = datetime.now().isoformat()

        # Handle different response formats
        if "text" in response:
            # Try to parse as JSON if it looks like JSON
            text = response["text"]
            if text.strip().startswith("{"):
                try:
                    parsed = json.loads(text)
                    return {
                        "query": query,
                        "domain": domain,
                        "results": parsed.get("findings", []),
                        "sources": parsed.get("sources", []),
                        "recommendations": parsed.get("recommendations", []),
                        "warnings": parsed.get("warnings", []),
                        "timestamp": timestamp,
                        "model": self.model,
                        "enabled": True
                    }
                except json.JSONDecodeError:
                    pass

            # Fallback: Convert text to structured format
            return {
                "query": query,
                "domain": domain,
                "results": [
                    {
                        "title": "Research Results",
                        "summary": text,
                        "relevance": "high"
                    }
                ],
                "sources": [],
                "timestamp": timestamp,
                "model": self.model,
                "enabled": True
            }

        # Direct JSON response
        elif "findings" in response:
            return {
                "query": query,
                "domain": domain,
                "results": response.get("findings", []),
                "sources": response.get("sources", []),
                "recommendations": response.get("recommendations", []),
                "warnings": response.get("warnings", []),
                "timestamp": timestamp,
                "model": self.model,
                "enabled": True
            }

        # Unexpected format
        else:
            self.logger.warning(f"Unexpected response format: {response.keys()}")
            return self._empty_response(query, domain, message="Unexpected response format")

    def _empty_response(
        self,
        query: str,
        domain: Optional[str] = None,
        message: str = None,
        error: str = None
    ) -> Dict[str, Any]:
        """
        Create an empty response structure.

        Args:
            query: Original query
            domain: Optional domain
            message: Optional message
            error: Optional error message

        Returns:
            Empty response dict
        """
        result = {
            "query": query,
            "domain": domain,
            "results": [],
            "sources": [],
            "timestamp": datetime.now().isoformat(),
            "model": self.model,
            "enabled": False
        }

        if message:
            result["message"] = message
        if error:
            result["error"] = error

        return result


# Helper function for testing Gemini CLI integration
async def test_gemini_cli_integration():
    """
    Test function to verify Gemini CLI integration.

    Run this to test if the integration is working correctly.
    """
    import sys

    # Setup logging
    logging.basicConfig(level=logging.DEBUG)

    # Test configuration
    config = {
        "gemini": {
            "use_cli": True,
            "cli_model": "gemini-2.5-flash",  # Use faster model for testing
            "cli_timeout": 30,
            "cache_results": False
        }
    }

    # Create researcher
    researcher = GeminiResearcher(config)

    # Wait for CLI check
    await asyncio.sleep(1)

    if not researcher.is_enabled():
        print("❌ Gemini CLI is not available or not configured")
        sys.exit(1)

    print("✅ Gemini CLI is available")

    # Test 1: Simple research
    print("\n📚 Test 1: Simple research query...")
    result = await researcher.research(
        query="What are the best practices for JWT authentication?",
        domain="Security"
    )

    if result.get("results"):
        print(f"✅ Got {len(result['results'])} results")
        for finding in result['results'][:2]:  # Show first 2
            print(f"  - {finding.get('title', 'No title')}")
    else:
        print("❌ No results returned")

    # Test 2: Best practices research
    print("\n📚 Test 2: Best practices research...")
    result = await researcher.research_best_practices(
        domain="API Design",
        technology_stack=["Node.js", "Express", "PostgreSQL"]
    )

    if result.get("results"):
        print(f"✅ Got {len(result['results'])} best practices")
    else:
        print("❌ No best practices returned")

    # Test 3: Security recommendations
    print("\n📚 Test 3: Security recommendations...")
    result = await researcher.research_security_recommendations(
        vulnerability_type="SQL Injection"
    )

    if result.get("results"):
        print(f"✅ Got {len(result['results'])} security recommendations")
    else:
        print("❌ No security recommendations returned")

    print("\n✅ All tests completed!")


if __name__ == "__main__":
    # Run tests
    asyncio.run(test_gemini_cli_integration())