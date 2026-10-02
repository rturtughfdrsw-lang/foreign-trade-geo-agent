# Repository Guidelines

## Project Purpose

This Python 3.12 project builds a deterministic SEO workflow for B2B foreign-trade websites: crawl and extract site evidence, research the industry, plan content and site changes, draft content, persist traceable artifacts, and create an explicitly approved WordPress draft. The current product priority is a mature, commercially viable SEO Agent MVP. Keep the repository's existing GEO / AI Visibility functionality isolated and properly maintained; unless the user explicitly requests it or the SEO MVP itself depends on it, do not expand GEO / AI Visibility in current work.

## Architecture

- `src/foreign_trade_geo_agent/core/` owns provider-independent domain models, validation, safety invariants, and `Protocol` ports. Keep it free of workflow, adapter, storage, reporting, and concrete I/O dependencies.
- `workflows/` implements fixed, bounded orchestration against core models and ports. The main planning chain is crawl -> site-content packet -> industry research -> content opportunities -> change plan -> content drafts, then stops for human review. Visibility and site-optimization flows are separate branches. WordPress delivery is a separate, explicitly approved step.
- `adapters/` implements external boundaries (HTTP/DNS, extraction, DeepSeek, Tavily, Perplexity, geo-optimizer, and WordPress REST) and maps their data into core contracts. Do not leak provider-specific response types into core or workflows.
- `storage/` implements artifact serialization and the synchronous `HistoryStore` port with SQLite. Preserve append-only artifacts, explicit run/attempt state transitions, and sanitized persisted failures.
- `reporting/` builds and renders views from validated core reports. `runtime.py` is the composition root that wires concrete adapters, storage, and workflows; `cli.py` is the `plan` / `deliver` entry point.
- Dependencies point inward: workflows, adapters, storage, and reporting may depend on core; core must not depend on them. Concrete implementations are selected at the runtime boundary, not inside domain logic.

## Development Rules

- Prefer the smallest local change compatible with the existing contracts and fixed-workflow design. Do not perform broad refactors without a demonstrated need.
- Preserve fail-closed validation, bounded resource/input/output behavior, sanitized errors, evidence traceability, and the human-review boundary. The current MVP's WordPress delivery is create-only and draft-only. Do not expand it to modify existing content, publish automatically, or retry ambiguous deliveries unless the task explicitly changes that product boundary and the user explicitly authorizes the related live action.
- Add or update focused tests for features and bug fixes. Do not weaken correctness, remove valid assertions, or bypass safety checks merely to make tests pass.
- Keep third-party and network behavior behind existing core ports and adapters. Extend a provider-independent contract only when the domain genuinely requires it.

## Testing and Verification

Tests use the standard-library `unittest` framework. From the repository root, after the editable install described in `README.md`:

```powershell
# Targeted module (choose the module(s) matching the change)
.\.venv\Scripts\python.exe -m unittest tests.test_<area> -v

# Full suite
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Run targeted tests while iterating and verification proportionate to the final change before completion; use the full suite for broad or cross-cutting changes. `scripts/verify_*.py` are opt-in live/integration checks, often requiring credentials or network access, and are not substitutes for unit tests. Never claim tests or the full suite pass unless that exact verification was run and its result observed; report failures accurately.

## External Side Effects and Secrets

- By default, do not call real production APIs, crawl real customer sites, modify WordPress, create remote drafts, publish content, or perform other irreversible external actions. Require explicit user authorization for the specific live action.
- Prefer mocks, fakes, injected transports/resolvers, temporary SQLite databases, and local fixtures under `tests/fixtures/`.
- Never print, commit, persist in artifacts, or hard-code API keys, tokens, passwords, cookies, authorization headers, or raw secret-bearing provider responses. Keep local credentials in the ignored `.env`; only placeholder names belong in `.env.example`.

## Git Rules

- Read-only inspection with `git status`, `git diff`, and `git log` is allowed by default.
- Do not commit, push, merge, rebase, delete branches, or otherwise rewrite Git history unless the user explicitly requests it.
- Preserve all existing user changes. Inspect the working tree before editing and never overwrite or discard unrelated uncommitted work.

## Working with Skills

- Use an enabled Superpowers skill when it clearly matches the task, without forcing a ceremonial brainstorm -> plan -> TDD -> review pipeline onto simple, bounded work.
- For bugs and test failures, start with Systematic Debugging. Use Writing Plans for genuinely complex, multi-step implementations. Apply Test-Driven Development to feature and bug-fix work when appropriate to the task, and use Verification Before Completion before claiming success.
- Follow the skill's instructions without copying its general SOP into repository documentation or inventing project-specific process that the repository does not need.

## Completion Report

For development tasks, briefly report:

- changed files;
- implemented behavior;
- tests and verification actually run, including failures;
- remaining limitations or risks.
