#!/usr/bin/env python
"""
Simple test script for Gemini CLI in WSL environment.
"""

import asyncio
import subprocess
import json
import platform

async def test_direct_npx():
    """Test direct npx call with a simple prompt."""
    print("Testing direct npx call...")

    # Use npx.cmd on Windows
    npx_cmd = "npx.cmd" if platform.system() == "Windows" else "npx"

    cmd = [
        npx_cmd, "@google/gemini-cli",
        "What is 2+2? Reply with just the number.",
        "--output-format", "json"
    ]

    print(f"Command: {' '.join(cmd[:3])}...")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        print(f"Return code: {result.returncode}")

        if result.returncode == 0:
            print("Success! Output:")
            try:
                output = json.loads(result.stdout)
                print(json.dumps(output, indent=2)[:500])  # First 500 chars
            except json.JSONDecodeError:
                print(result.stdout[:500])
        else:
            print(f"Error: {result.stderr}")

    except subprocess.TimeoutExpired:
        print("Command timed out after 30 seconds")
    except Exception as e:
        print(f"Error: {e}")

async def test_async_subprocess():
    """Test async subprocess with npx."""
    print("\n" + "="*60)
    print("Testing async subprocess...")

    # Use npx.cmd on Windows
    npx_cmd = "npx.cmd" if platform.system() == "Windows" else "npx"

    cmd = [
        npx_cmd, "@google/gemini-cli",
        "List 3 benefits of unit testing. Format as JSON with 'benefits' array.",
        "--output-format", "json",
        "--model", "gemini-2.5-flash"
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=30
        )

        if process.returncode == 0:
            print("Success! Output:")
            output_text = stdout.decode().strip()
            try:
                output = json.loads(output_text)
                print(json.dumps(output, indent=2)[:500])
            except json.JSONDecodeError:
                print(output_text[:500])
        else:
            print(f"Error: {stderr.decode()}")

    except asyncio.TimeoutError:
        print("Command timed out")
        process.kill()
        await process.communicate()
    except FileNotFoundError:
        print("npx command not found in PATH")
    except Exception as e:
        print(f"Error: {e}")

async def main():
    print("="*60)
    print("Gemini CLI Test (WSL Environment)")
    print("="*60)

    # Test 1: Direct subprocess call
    await test_direct_npx()

    # Test 2: Async subprocess
    await test_async_subprocess()

    print("\n" + "="*60)
    print("Test completed")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())