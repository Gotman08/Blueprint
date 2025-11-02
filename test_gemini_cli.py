#!/usr/bin/env python
"""
Test script for Gemini CLI integration.

Run this script to verify that the Gemini CLI integration is working correctly.
Usage: python test_gemini_cli.py
"""

import sys
import os
import asyncio
import logging

# Add the orchestrator directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'orchestrator'))

from agents.gemini_researcher import GeminiResearcher


async def main():
    """Main test function."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("Testing Gemini CLI Integration")
    print("=" * 60)

    # Test configuration
    config = {
        "gemini": {
            "use_cli": True,
            "cli_model": "gemini-2.5-flash",  # Use faster model for testing
            "cli_timeout": 30,
            "cache_results": False,
            "max_retries": 2
        }
    }

    # Create researcher instance
    print("\n[INIT] Initializing GeminiResearcher...")
    researcher = GeminiResearcher(config)

    # Wait for CLI availability check
    await asyncio.sleep(1)

    # Check if enabled
    if not researcher.is_enabled():
        print("\n[ERROR] Gemini CLI is not available or not configured!")
        print("\nPlease ensure:")
        print("1. Gemini CLI is installed: npm install -g @google/gemini-cli")
        print("2. You are authenticated: gemini auth login")
        print("3. The 'gemini' command is in your PATH")
        return 1

    print("[OK] Gemini CLI is available and configured")

    # Test 1: Simple research query
    print("\n" + "=" * 60)
    print("Test 1: Simple Research Query")
    print("-" * 60)

    try:
        result = await researcher.research(
            query="What are the best practices for JWT authentication in web applications?",
            domain="Security"
        )

        if result.get("results"):
            print(f"[OK] Research successful! Got {len(result['results'])} findings")
            print("\nFindings:")
            for i, finding in enumerate(result['results'][:3], 1):
                print(f"\n{i}. {finding.get('title', 'Untitled')}")
                summary = finding.get('summary', '')
                if summary:
                    # Truncate long summaries
                    if len(summary) > 200:
                        summary = summary[:197] + "..."
                    print(f"   {summary}")
                print(f"   Relevance: {finding.get('relevance', 'unknown')}")
        else:
            print("[WARNING] No results returned (but no error)")
            if result.get("message"):
                print(f"Message: {result['message']}")
            if result.get("error"):
                print(f"Error: {result['error']}")
    except Exception as e:
        print(f"[ERROR] Test 1 failed: {e}")
        import traceback
        traceback.print_exc()

    # Test 2: Best practices research
    print("\n" + "=" * 60)
    print("Test 2: Best Practices Research")
    print("-" * 60)

    try:
        result = await researcher.research_best_practices(
            domain="REST API Design",
            technology_stack=["Node.js", "Express", "PostgreSQL"]
        )

        if result.get("results"):
            print(f"[OK] Best practices research successful! Got {len(result['results'])} practices")
            print("\nBest Practices:")
            for i, finding in enumerate(result['results'][:3], 1):
                print(f"{i}. {finding.get('title', 'Untitled')}")
        else:
            print("[WARNING] No best practices returned")
    except Exception as e:
        print(f"[ERROR] Test 2 failed: {e}")

    # Test 3: Security recommendations
    print("\n" + "=" * 60)
    print("Test 3: Security Recommendations")
    print("-" * 60)

    try:
        result = await researcher.research_security_recommendations(
            vulnerability_type="SQL Injection"
        )

        if result.get("results"):
            print(f"[OK] Security research successful! Got {len(result['results'])} recommendations")
            print("\nSecurity Recommendations:")
            for i, finding in enumerate(result['results'][:3], 1):
                print(f"{i}. {finding.get('title', 'Untitled')}")
        else:
            print("[WARNING] No security recommendations returned")
    except Exception as e:
        print(f"[ERROR] Test 3 failed: {e}")

    # Test 4: Library documentation
    print("\n" + "=" * 60)
    print("Test 4: Library Documentation Research")
    print("-" * 60)

    try:
        result = await researcher.research_library_documentation(
            library_name="jsonwebtoken",
            use_case="user authentication with refresh tokens"
        )

        if result.get("results"):
            print(f"[OK] Documentation research successful! Got {len(result['results'])} sections")
            print("\nDocumentation Sections:")
            for i, finding in enumerate(result['results'][:3], 1):
                print(f"{i}. {finding.get('title', 'Untitled')}")
        else:
            print("[WARNING] No documentation returned")
    except Exception as e:
        print(f"[ERROR] Test 4 failed: {e}")

    # Test 5: Batch research (parallel)
    print("\n" + "=" * 60)
    print("Test 5: Batch Research (Parallel Queries)")
    print("-" * 60)

    try:
        queries = [
            {
                "query": "OAuth 2.0 best practices",
                "domain": "Authentication"
            },
            {
                "query": "Rate limiting strategies for APIs",
                "domain": "Security"
            },
            {
                "query": "Database connection pooling",
                "domain": "Performance"
            }
        ]

        print(f"Running {len(queries)} queries in parallel...")
        results = await researcher.batch_research(queries)

        print(f"[OK] Batch research completed! Got {len(results)} results")
        for i, (query, result) in enumerate(zip(queries, results), 1):
            findings_count = len(result.get("results", []))
            print(f"{i}. '{query['query']}': {findings_count} findings")
    except Exception as e:
        print(f"[ERROR] Test 5 failed: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    # Run the async main function
    exit_code = asyncio.run(main())
    sys.exit(exit_code)