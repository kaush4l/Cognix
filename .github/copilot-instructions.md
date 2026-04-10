# Project Guidelines

## Core Ideology
- Never throw errors in project code. The project must degrade gracefully and continue operating.
- Assume inputs are correct before runtime. Do not add defensive rejection paths, strict validation gates, or failure-oriented control flow unless explicitly requested.
- Keep the code minimalist. Every line must add direct value to the current behavior.
- Do not expand the architecture just because a generic abstraction is possible. Preserve the current small, intentional scaffold.
- Prefer thoughtful, project-specific behavior over broad framework-like generalization.

## Architecture Pattern
- Follow the existing module pattern in `engine.py`, `inference.py`, and `responses.py`.
- Each module should have a base class that holds the shared footprint, common utilities, and default behavior for that module.
- Concrete subclasses should inherit that footprint and implement only the minimum behavior they actually need.
- Base classes exist as contracts by convention and shared utility holders. They are not expected to be instantiated directly.
- Do not turn base classes into runtime enforcement points with `NotImplementedError`, assertions, or strict abstract machinery unless explicitly requested.

## Error Handling And Fallbacks
- Never raise project-level exceptions for normal control flow.
- Never use `NotImplementedError` in base methods in this project.
- Prefer empty strings, empty lists, empty dicts, default model instances, or `None` as graceful fallbacks when needed.
- If model output is incomplete or slightly malformed, coerce it and continue instead of failing, retrying, or rejecting.
- Do not add blanket retry loops or aggressive recovery orchestration unless the task explicitly asks for it.

## Response Parsing Rules
- Response parsing should be permissive and best-effort.
- Missing keys from model output are expected in large-context situations and should not break the flow.
- `action` and `answer` are the primary fields that matter for project behavior.
- `observation` and `thinking` are useful for context expansion, but they are secondary to `action` and `answer`.
- Prefer partial success over strict correctness when parsing model output.

## Implementation Style
- Preserve the current concise style. Avoid large helper hierarchies, excessive indirection, and speculative abstractions.
- Do not add code for hypothetical future use unless the task clearly requires it.
- Prefer simple factories and direct branching over elaborate registration systems when the repo is still small.
- Hardcoded project flows are acceptable when they reflect the intended assistant behavior and keep the code simpler.
- Use existing patterns before inventing new ones.

## What To Avoid
- Do not add runtime-heavy validation layers.
- Do not add exception-first logic.
- Do not add abstract base class ceremony that increases rigidity without improving the current footprint.
- Do not widen scope by building extra subsystems, plugins, or configuration layers that the task did not ask for.
- Do not rewrite minimalist scaffolding into a larger "clean architecture" or framework-style system.

## When Modifying Existing Files
- Extend the current structure instead of refactoring it into a different style.
- Keep shared utilities in the base class for that module.
- Keep subclass implementations small and behavior-focused.
- If a graceful fallback is possible, prefer it over interruption.
- If a change risks expanding the code noticeably, choose the smaller implementation unless a larger one is clearly necessary.