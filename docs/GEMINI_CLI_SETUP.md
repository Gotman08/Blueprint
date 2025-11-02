# Gemini CLI Integration Guide for Blueprint

## Overview

Blueprint now supports Gemini CLI for external research during the cahiers des charges generation phase. This allows analyst agents to enrich their specifications with current best practices, security recommendations, and documentation references.

## Prerequisites

1. **Node.js**: Ensure Node.js is installed (version 20 or higher)
2. **NPM/NPX**: Should be included with Node.js installation
3. **Windows/WSL**: The system works on both Windows and WSL environments

## Installation Steps

### 1. Gemini CLI Installation

You have two options:

#### Option A: Use NPX (Recommended - No Installation Required)
```bash
# Test that npx is available
npx --version

# Gemini CLI will be automatically downloaded when first used
npx @google/gemini-cli --version
```

#### Option B: Global Installation
```bash
# Install globally
npm install -g @google/gemini-cli

# Verify installation
gemini --version
```

### 2. Authentication

Choose one of the following authentication methods:

#### Method 1: OAuth Login (Recommended)
```bash
# Using npx
npx @google/gemini-cli auth login

# Or if installed globally
gemini auth login
```
This will open a browser for Google authentication.

#### Method 2: API Key (Environment Variable)
```bash
# Windows (CMD)
set GEMINI_API_KEY=your_api_key_here

# Windows (PowerShell)
$env:GEMINI_API_KEY="your_api_key_here"

# Linux/WSL
export GEMINI_API_KEY=your_api_key_here
```

Get your API key from: https://aistudio.google.com/apikey

### 3. Test the Setup

Run the test script to verify everything is working:

```bash
python test_gemini_simple.py
```

Or test directly with Gemini CLI:

```bash
# Windows
npx.cmd @google/gemini-cli "Hello, are you working?" --output-format json

# Linux/WSL
npx @google/gemini-cli "Hello, are you working?" --output-format json
```

## Configuration

### Enable Gemini in Pipeline Configuration

Edit `config/pipeline_config.yaml`:

```yaml
# Gemini Configuration
gemini:
  use_cli: true  # Use CLI instead of API
  enabled: true  # Enable Gemini research
  cli_model: "gemini-2.5-pro"  # or "gemini-2.5-flash" for faster responses
  cli_timeout: 30  # Timeout in seconds
  cache_results: false  # Set to true to cache responses
  max_retries: 2  # Retry attempts on failure

# Phase 0 Configuration
phase0:
  enable_gemini_research: true  # Enable for analyst agents
  gemini_model: "gemini-2.5-pro"  # Model for research
```

## Usage

Once configured and enabled, the system will automatically use Gemini CLI during Phase 0 (Master Analysts) to:

1. **Research Best Practices**: When creating cahiers des charges, analysts will query for current best practices
2. **Security Recommendations**: For security-related domains, fetch OWASP and security guidelines
3. **Documentation References**: Find relevant documentation for libraries and frameworks
4. **Technology Stack Analysis**: Research specific technologies mentioned in the project

## Features

### Research Methods Available

The `GeminiResearcher` class provides several specialized research methods:

- `research(query, domain, task_context)`: General research on any topic
- `research_best_practices(domain, technology_stack)`: Domain-specific best practices
- `research_security_recommendations(vulnerability_type)`: Security-focused research
- `research_library_documentation(library_name, use_case)`: Library/framework documentation
- `batch_research(queries)`: Multiple parallel queries

### Prompt Templates

The system uses optimized prompt templates for different types of research:

- **General Research**: Comprehensive analysis with findings, recommendations, and warnings
- **Best Practices**: Architecture patterns, security considerations, performance strategies
- **Security Analysis**: OWASP relevance, attack vectors, mitigation strategies
- **Documentation Search**: Latest features, API references, integration patterns

## Troubleshooting

### Common Issues and Solutions

1. **"Gemini CLI not found"**
   - Ensure Node.js and npm are in your PATH
   - On Windows, the system will automatically use `npx.cmd`
   - Try using the full path: `C:\Program Files\nodejs\npx.cmd`

2. **"Authentication required"**
   - Run `npx @google/gemini-cli auth login`
   - Or set the GEMINI_API_KEY environment variable
   - Check `~/.gemini/settings.json` for configuration

3. **"Timeout errors"**
   - Increase `cli_timeout` in configuration
   - Use `gemini-2.5-flash` model for faster responses
   - Check internet connection

4. **"Command not found in WSL"**
   - Ensure you're using `npx.cmd` on Windows
   - The system automatically detects Windows and uses the correct command

## Rate Limits

- **Free Tier**: 60 requests/minute, 1,000 requests/day
- **With Code Assist License**: Higher limits based on organization plan

## Testing Integration

Run the comprehensive test suite:

```bash
# Simple connectivity test
python test_gemini_simple.py

# Full integration test
python test_gemini_cli.py
```

## Security Considerations

- API keys are never stored in code
- Use environment variables or OAuth authentication
- Research results are logged to database for audit trail
- Sensitive queries can be filtered in configuration

## Support

- **Gemini CLI Issues**: https://github.com/google-gemini/gemini-cli/issues
- **Blueprint Integration**: Check logs in `logs/` directory
- **Authentication Help**: Run `npx @google/gemini-cli auth status`

## Next Steps

1. Authenticate with Gemini CLI
2. Enable in configuration (`enabled: true`)
3. Run a test pipeline to see research in action
4. Monitor `logs/pipeline.log` for research activities

## Example Output

When enabled, you'll see research being performed in Phase 0:

```
[INFO] [Security-Analyst] Performing external research...
[INFO] Gemini CLI found (npx): 0.11.3
[INFO] Research successful! Got 5 findings
[INFO] Research stored in database for CAHIER-Security
```

The research results will be incorporated into the generated cahiers des charges, providing agents with additional context and best practices.