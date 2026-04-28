# AGENTS.md

## Scope

These instructions apply to the whole repository.

## Default navigation rules

- Prioritize source code, tests, launcher scripts, and project documentation.
- Do not inspect or index heavy/generated directories unless the user explicitly asks for them.

## Skip by default

- `Persistence/`
- `Results/`
- `Internal_logs/`
- `GUI/robust-6g-dashboard/.next/`
- `GUI/robust-6g-dashboard/dist/`
- Any `__pycache__/` directory
- Minified bundles, build artifacts, lockfiles, and large generated assets unless they are directly relevant

## When to enter skipped paths

- The user explicitly references a file inside them
- A failing test, stack trace, or import path points there
- The task is about persistence, generated results, or frontend build output

## Search strategy

- Start from the files named in the request and nearby modules
- Prefer targeted searches over repository-wide scans
- Treat skipped paths as opt-in, not part of the default context
