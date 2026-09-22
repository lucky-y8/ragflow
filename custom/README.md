# Custom development

All new project-specific features, tests, scripts, configuration templates, and documentation belong under `custom/`.

| Directory | Purpose |
| --- | --- |
| `backend_python/` | Custom Python backend features |
| `backend_go/` | Custom Go backend features |
| `frontend/` | Custom frontend features |
| `scripts/` | Local environment management, dependency sync, resource download, and verification |
| `docs/` | Requirements, design, API, development, and deployment documentation |

Add implementations only when needed; a feature does not need both backend languages. The backend and frontend directories are placeholders and are not wired into the running services yet.

Keep upstream integration changes small and document required integration points in `docs/`. Do not copy the upstream application into these directories. Keep secrets and runtime data out of version control.

## Local environment

See [WSL local environment](docs/local-environment.md). Run `./custom/scripts/manage.py start` from the repository root. Runtime data, installed tools, caches, and credentials remain in the Git-ignored `.local-dev/` directory. The original application still reads configuration, virtual environments, and model resources from its existing paths.
