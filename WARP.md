# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Common Development Commands

### Build & Installation
```bash
# Install CAI from PyPI
pip install cai-framework

# Install for development (with all dependencies)
pip install -e .

# Install with optional extensions
pip install -e ".[voice,viz,discord]"

# Sync all dependencies using uv (recommended for development)
make sync
```

### Running CAI
```bash
# Launch CAI CLI
cai

# Run with specific environment variables
CAI_MODEL=gpt-4o CAI_AGENT_TYPE=redteam_agent cai

# Run CAI with tracing enabled
CAI_TRACING=true cai

# Run with streaming disabled
CAI_STREAM=false cai
```

### Testing
```bash
# Run all tests
make tests

# Run specific test file
pytest tests/agents/test_agent_config.py

# Run tests with coverage
make coverage

# Run tests with inline snapshots
make snapshots-fix  # Fix snapshots
make snapshots-create  # Create new snapshots

# Run tests on Python 3.9 (compatibility testing)
make old_version_tests
```

### Code Quality
```bash
# Format code
make format

# Run linter
make lint

# Type checking
make mypy
```

### Documentation
```bash
# Build docs
make build-docs

# Serve docs locally (view at http://localhost:8000)
make serve-docs

# Deploy docs to GitHub Pages
make deploy-docs
```

## High-Level Architecture

CAI is built on 7 core pillars for cybersecurity AI operations:

### 1. **Agents** (`src/cai/agents/`)
- Implement ReACT (Reasoning and Action) agent model
- Each agent is a specialized cybersecurity expert
- Key agents include:
  - `one_tool_agent`: Single-purpose focused agent
  - `redteam_agent`: Offensive security specialist
  - Pattern-based agents in `patterns/` for complex multi-agent workflows

### 2. **Tools** (`src/cai/tools/`)
Tools are organized by security kill chain phases:
- **Reconnaissance** (`reconnaissance/`): nmap, bbot, shodan, crypto_tools
- **Command & Control** (`command_and_control/`): sshpass, remote execution
- **Network** (`network/`): capture_traffic, analysis tools
- **Web** (`web/`): google_search, headers analysis, webshell utilities
- **Misc** (`misc/`): code_interpreter, reasoning, RAG capabilities

### 3. **Patterns** (`src/cai/agents/patterns/`)
Agentic patterns define multi-agent coordination:
- Swarm (decentralized)
- Hierarchical (structured delegation)
- Chain-of-Thought (sequential)
- Recursive (self-refinement)
- Parallelization (concurrent execution)

### 4. **SDK** (`src/cai/sdk/`)
Core framework components:
- `agents/`: Agent base classes and interfaces
- `agents/models/`: LLM model integrations (300+ models via LiteLLM)
- `agents/mcp/`: Model Context Protocol support
- `agents/tracing/`: OpenTelemetry-based observability

### 5. **REPL** (`src/cai/repl/`)
Interactive command-line interface:
- `commands/`: Built-in commands (/agent, /model, /config, /history, etc.)
- `ui/`: Terminal UI components and aesthetics
- Human-In-The-Loop (HITL) via Ctrl+C interruption

### 6. **Internal** (`src/cai/internal/`)
Core functionality:
- Metrics collection
- Logging infrastructure
- Component management
- Telemetry (can be disabled via CAI_TELEMETRY=False)

### 7. **Prompts** (`src/cai/prompts/`)
Agent prompt templates and system instructions

## Key Design Principles

1. **Modular Agent Architecture**: Each agent is self-contained with specific expertise
2. **Tool Integration**: Easy to add custom tools via function decorators
3. **Pattern-Based Coordination**: Flexible multi-agent workflows
4. **HITL by Design**: Human oversight integrated at core (Ctrl+C at any time)
5. **Extensive Model Support**: 300+ models through LiteLLM integration
6. **Tracing Built-in**: Phoenix/OpenTelemetry for debugging and optimization

## Environment Configuration

Create a `.env` file based on `.env.example`:

```bash
# Core API Keys
OPENAI_API_KEY="sk-..."
ANTHROPIC_API_KEY="..."
ALIAS_API_KEY="..."  # For alias0 model

# Model Configuration
CAI_MODEL="gpt-4o"  # or "claude-3-5-sonnet", "deepseek-v3", etc.
CAI_AGENT_TYPE="redteam_agent"

# Operational Settings
CAI_STREAM=false  # Enable/disable streaming
CAI_TRACING=true  # Enable tracing
CAI_DEBUG=1  # Debug level (0-2)
CAI_TELEMETRY=true  # Usage analytics

# Memory & State
CAI_MEMORY="episodic"  # Memory mode
CAI_STATE=true  # Stateful mode
```

## MCP (Model Context Protocol) Integration

CAI supports MCP for external tool integration:

```bash
# Load MCP server via SSE
CAI>/mcp load http://localhost:9876/sse burp

# Load MCP server via STDIO
CAI>/mcp load stdio myserver python mcp_server.py

# Add MCP tools to agent
CAI>/mcp add burp redteam_agent
```

## Development Tips

1. **Virtual Environment**: Always use a fresh virtual environment when updating CAI
2. **Dev Container**: VS Code dev container is available for consistent development environment
3. **Testing**: Run tests before commits, especially for tool modifications
4. **Tracing**: Use `CAI_TRACING=true` to debug agent behavior and tool usage
5. **Custom Tools**: Add new tools in appropriate category under `src/cai/tools/`
6. **Agent Patterns**: Study examples in `examples/agent_patterns/` for multi-agent workflows

## CI/CD Pipeline

The project uses GitLab CI with comprehensive test coverage:
- Unit tests for all major components
- Tool-specific integration tests
- Agent behavior validation
- Pattern execution tests
- MCP integration tests

See `.gitlab-ci.yml` and `ci/test/.test.yml` for full test configuration.

## Important Files

- `src/cai/cli.py`: Main CLI entry point
- `src/cai/core.py`: Core agent execution logic
- `src/cai/util.py`: Utility functions
- `pyproject.toml`: Project dependencies and configuration
- `Makefile`: Development commands
