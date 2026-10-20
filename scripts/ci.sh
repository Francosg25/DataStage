#!/usr/bin/env bash
set -euo pipefail
workspace="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$workspace"
python -m venv .venv-ci
source .venv-ci/bin/activate
python -m pip install --no-deps -r backend/requirements.lock
python -m pip check
python scripts/check_dependency_lock.py
python -m ruff check backend
python -m ruff check deploy scripts --select E4,E7,E9,F
python -m pytest backend/tests scripts/tests
cd frontend
npm ci
npm test -- --watch=false
npm run build
cd "$workspace"
python scripts/build_release.py --version "${DATASTAGE_RELEASE_VERSION:-ci}"
