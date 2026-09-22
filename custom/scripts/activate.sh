# Source this file from Bash; changes apply only to the current shell.
RAGFLOW_LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
set -a
source "$RAGFLOW_LOCAL_ROOT/.local-dev/config/runtime.env"
set +a
source "$RAGFLOW_LOCAL_ROOT/.venv/bin/activate"
