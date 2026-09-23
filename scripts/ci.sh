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
python -m pytest backend/tests
cd frontend
npm ci
npm test -- --watch=false
npm run build
cd "$workspace"
# Optional SQL integration is activated by DATASTAGE_TEST_SQLSERVER_URL.
# Building is explicit; this script never deploys or pushes an image.
if [[ "${DATASTAGE_BUILD_IMAGES:-false}" == "true" ]]; then
  docker build -f deploy/Dockerfile.backend -t datastage-backend:ci .
  docker build -f deploy/Dockerfile.frontend -t datastage-frontend:ci .
fi
