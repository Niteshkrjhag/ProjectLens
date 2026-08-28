#!/usr/bin/env bash

set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON_BIN:-python3.12}"

if ! command -v "${python_bin}" >/dev/null 2>&1; then
  echo "${python_bin} is required. Set PYTHON_BIN to a Python 3.12 executable." >&2
  exit 1
fi

cd "${project_root}"
"${python_bin}" -m venv .venv
"${project_root}/.venv/bin/python" -m pip install -r backend/requirements.txt
npm --prefix frontend ci

echo "ProjectLens is ready. Run:"
echo "  PYTHONPATH=backend/src .venv/bin/python -m projectlens.cli demo --source 'testing dataset/simple/general' --state-dir data/dry-run --approve-all"
