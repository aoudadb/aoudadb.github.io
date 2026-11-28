#!/usr/bin/env bash
# The docs' lane (aouda Operability S03): every check, the exit the worst. See scripts/ci.py.
set -euo pipefail
exec python3 -u "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/ci.py" "$@"
