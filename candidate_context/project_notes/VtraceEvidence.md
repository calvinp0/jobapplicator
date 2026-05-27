# vtrace: Personal Project Evidence

## One-Line Summary

`vtrace` is a local-first TypeScript/Bun developer tool that builds a deterministic structural index of a source repository and exposes that index through a CLI, MCP server, and local VS Code extension so coding agents and developers can retrieve compact, source-backed code context without using a remote indexing service.

## What The Project Does

`vtrace` solves a practical problem in AI-assisted software development: large repositories cannot be pasted wholesale into a prompt, and plain text search does not understand code structure. The tool indexes a local repository, extracts symbols and relationships, and returns bounded context packages that are useful for debugging, refactoring, explaining code, and planning changes.

The project supports TypeScript, Python, and Cython source analysis. It uses Tree-sitter parsers to extract symbols such as functions, classes, methods, interfaces, imports, and structural containment edges. That data is stored in repo-local SQLite state under `.vtrace/`, then surfaced through deterministic search, impact graphs, skeleton views, context capsules, session memory, project rules, and MCP tools.

The design emphasizes local execution, inspectable outputs, reproducibility, and honest boundaries. It does not claim semantic execution tracing or ML-powered understanding. Instead, it provides reliable structural evidence that an agent or developer can inspect.

## Why It Is Resume-Worthy

This is not a toy script. It is a multi-surface developer tool with a real product shape:

- A command-line interface with setup, indexing, status, watch, daemon, capsule, impact graph, skeleton, handoff, rules, and pipeline commands.
- An MCP server exposing repository intelligence to tools such as Claude Code and Codex.
- A private/local VS Code extension surface for invoking the tool from an editor.
- A deterministic indexing pipeline backed by Tree-sitter and SQLite.
- A memory layer for observations, stale-state tracking, session compression, passive tool-call capture, and conservative project-rule surfacing.
- A validation strategy with synthetic fixtures, mixed Python/Cython fixtures, schema checks, and regression tests.
- Documentation for setup, CLI usage, MCP tools, troubleshooting, release readiness, and product truth boundaries.

## Core Engineering Work

### Repository Indexing And Parsing

Built a local indexing system that scans repositories, detects supported source files, parses source code with Tree-sitter, extracts symbols, and stores structural relationships in SQLite. The index is deterministic and repo-local, which makes results reproducible and avoids dependence on external services.

Skills demonstrated:

- AST parsing with Tree-sitter
- TypeScript system design
- Symbol modeling and graph-like data representation
- Content-addressed identity and deterministic hashing
- SQLite schema design and persistence
- Multi-language parsing boundaries across TypeScript, Python, and Cython

### Structural Retrieval And Context Packaging

Implemented retrieval flows that turn a user task into compact source-backed context. `vtrace` can return file skeletons, impact graphs for exact symbols, bounded logic-flow paths, and budget-aware context capsules that include pivots, supporting code, surfaced memories, active project rules, and metadata explaining why items were selected.

Skills demonstrated:

- Search and ranking design
- Budget-aware context assembly
- Explainable retrieval outputs
- Graph-aware code navigation
- Developer-experience focused API design
- Practical tradeoffs around precision, recall, and deterministic behavior

### MCP Tooling For AI Coding Agents

Exposed the system through a stable MCP tool surface, including `run_pipeline`, `get_context_capsule`, `get_skeleton`, `get_impact_graph`, `search_logic_flow`, `index_status`, `workspace_setup`, `search_memory`, `save_observation`, and `expand_vexp_ref`.

This required designing schemas, validating inputs, formatting outputs, preserving backward-compatible aliases, and keeping tool behavior aligned with documentation.

Skills demonstrated:

- Model Context Protocol integration
- Schema design and compatibility management
- Agent-oriented tool design
- Structured JSON output contracts
- Defensive validation and error handling
- Integration testing around real tool behavior

### Memory, Sessions, And Project Rules

Built a deterministic memory layer for saved observations and passive tool-call summaries. Observations can be linked to files, symbols, and fully qualified names, then marked stale when indexed code changes. The project also includes session compression, passive observation consolidation, anti-pattern detection, progressive nudges, and explicit project-rule candidates promoted from repeated evidence.

Skills demonstrated:

- Durable local memory design
- Staleness tracking from structural diffs
- Session lifecycle modeling
- Conservative automation design
- Evidence-based rule generation
- Avoiding overclaiming in AI-adjacent systems

### Runtime, Watcher, And Developer Workflow

Implemented setup, status, watcher, daemon, and agent-config flows so the tool can be installed into a local repository and used repeatedly. The watcher is intentionally conservative by default: it marks the index stale when source files change, while auto-reindexing is explicit opt-in.

Skills demonstrated:

- CLI product design
- Local runtime orchestration
- File watching and freshness state
- Idempotent setup flows
- Developer ergonomics
- Safe defaults for local tooling

### Testing And Validation

The repository contains a broad test suite across parsing, indexing, CLI behavior, MCP tools, memory, project rules, runtime freshness, validation, VS Code extension behavior, and mixed-language fixtures. The project also includes a written validation strategy that explicitly avoids overfitting to one benchmark repository.

Skills demonstrated:

- Regression test design
- Fixture-driven parser validation
- Product truth auditing
- Schema and output contract testing
- Cross-module integration testing
- Documentation-driven release hardening

## Technical Stack

| Area | Technology / Approach |
| --- | --- |
| Runtime | Bun |
| Language | TypeScript |
| Parsing | Tree-sitter |
| Storage | SQLite / repo-local `.vtrace` state |
| Agent integration | MCP server |
| Editor integration | Local VS Code extension |
| Supported source languages | TypeScript, Python, Cython |
| Testing | Bun test, fixture-based regression tests |
| Documentation | Markdown docs, CLI guides, MCP references, validation plans |

## Skills I Can Claim From This Project

### Systems And Architecture

- Designed a layered local developer tool with indexing, retrieval, orchestration, memory, runtime, CLI, MCP, and editor-extension surfaces.
- Modeled code as symbols, files, edges, references, observations, sessions, and project rules.
- Balanced product ambition with conservative technical boundaries so outputs stay deterministic and inspectable.

### AI Tooling And Agent Infrastructure

- Built MCP tools that expose structured repository context to coding agents.
- Designed agent-facing outputs that include provenance, diagnostics, freshness, memory, and bounded deferred expansion references.
- Developed workflows for compact context delivery instead of naive full-repository prompting.

### Search, Retrieval, And Context Engineering

- Implemented structural retrieval over indexed code rather than relying only on grep-style text matching.
- Built budget-aware context capsules with inclusion reasons and compression fallbacks.
- Created impact and logic-flow tools for exact symbol-level navigation.

### Local-First Developer Experience

- Built a repo-local tool that does not require a hosted service.
- Implemented repeatable setup, status, indexing, watcher, daemon, and config flows.
- Produced documentation aimed at real users, including getting started, CLI usage, MCP references, troubleshooting, and release-readiness notes.

### Testing, Reliability, And Product Discipline

- Wrote and maintained tests across parser behavior, CLI commands, MCP outputs, memory behavior, runtime freshness, and VS Code integration.
- Used fixture repositories to validate TypeScript, Python, and Cython behavior.
- Performed product truth audits to align claims, docs, schemas, and implementation.

## Copy-Ready Resume Bullets

- Built `vtrace`, a local-first TypeScript/Bun code intelligence tool that indexes repositories with Tree-sitter and exposes deterministic structural context through a CLI, MCP server, and local VS Code extension.
- Designed a repo-local SQLite indexing pipeline for TypeScript, Python, and Cython that extracts symbols, imports, containment edges, and source metadata for reproducible code navigation.
- Implemented agent-facing MCP tools for context capsules, file skeletons, symbol impact graphs, bounded logic-flow search, index status, workspace setup, session memory, and deferred context expansion.
- Developed a budget-aware context packaging system that selects relevant code pivots and supporting evidence while preserving deterministic inclusion reasons and freshness diagnostics.
- Built a local memory layer for observations, passive tool-call capture, session compression, stale-state tracking, and evidence-based project-rule surfacing.
- Created a conservative watcher and runtime flow that tracks source changes, marks stale indexes, supports optional auto-reindexing, and keeps readiness visible through CLI and MCP diagnostics.
- Wrote fixture-driven tests and validation docs covering parser behavior, retrieval, MCP schema alignment, runtime freshness, memory behavior, VS Code integration, and mixed Python/Cython repositories.

## Short Interview Pitch

`vtrace` is a personal project I built to make AI coding workflows more grounded in local source evidence. Instead of uploading a repository to a remote service or dumping huge files into a prompt, it builds a deterministic local index, extracts code structure, and gives agents compact context through MCP tools. The interesting engineering work was in designing the indexing model, retrieval pipeline, context capsule format, stale-state tracking, memory layer, and product boundaries so the tool is useful without pretending to understand more than it actually does.

## Longer Interview Explanation

I built `vtrace` because AI coding assistants often need better repository context than plain text search can provide. The tool scans a repository, parses supported files with Tree-sitter, stores symbols and relationships in SQLite, and exposes that data through a CLI and MCP server. A user or agent can ask for a file skeleton, an impact graph for an exact symbol, a compact context capsule for a task, or a pipeline result that includes intent, relevant code, memory, rules, and diagnostics.

A major part of the project was product discipline. Since this is AI-adjacent tooling, I was careful not to overclaim semantic understanding. The system is deterministic, structural, and inspectable. It tracks when indexed files change, marks related observations stale, and surfaces evidence with clear limitations. That made the project a good exercise in both software architecture and responsible tool design.

## Evidence Map

| Capability | Representative Paths |
| --- | --- |
| CLI commands | `src/cli`, `src/cli/commands`, `bin/vtrace` |
| MCP tools | `src/mcp/tools.ts`, `docs/mcp_tools.md` |
| Parsing | `src/parsers`, `fixtures/python`, `fixtures/cython`, `fixtures/mixed_py_cython_repo` |
| Indexing | `src/indexer`, `src/fs`, `src/db` |
| Retrieval and capsules | `src/retrieval`, `src/capsule`, `src/capsuleProfiles`, `src/runPipeline` |
| Impact and flow | `src/impact`, `src/logicFlow`, `src/skeleton` |
| Memory and observations | `src/observations`, `src/memory`, `src/projectRules` |
| Runtime and freshness | `src/runtime`, `src/setup`, `docs/getting_started.md` |
| VS Code extension | `vscode-extension` |
| Validation and release discipline | `src/validation`, `docs/validation_strategy.md`, `docs/product_truth_audit_rc.md` |

## Suggested Portfolio Framing

Use this project as evidence for roles involving developer tools, AI infrastructure, code intelligence, backend TypeScript, local-first systems, agent tooling, search/retrieval, or platform engineering.

Best headline:

> Built a local-first code intelligence engine for AI coding agents, combining Tree-sitter parsing, SQLite-backed structural indexing, MCP tool integration, context packaging, memory, and deterministic repository diagnostics.

