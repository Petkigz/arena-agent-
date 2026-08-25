#!/usr/bin/env bash
# Installs the CI workflow definitions into .github/workflows/ and commits.
#
# WHY THIS EXISTS: the GitHub App token used by Arena lacks the `workflows`
# permission, so pushes containing .github/workflows files are rejected:
#   "refusing to allow a GitHub App to create or update workflow ... without
#    `workflows` permission"
# Once that permission is granted (GitHub → Settings → Developer settings →
# GitHub Apps, or reinstall the Arena connection with workflows checked),
# run this script from the repo root and push.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
mkdir -p .github/workflows
cp scripts/ci/frontend.yml .github/workflows/frontend.yml
cp scripts/ci/android.yml .github/workflows/android.yml
git add .github/workflows
git commit -m "ci: enable frontend and android workflows" || true
echo "Workflows installed and committed. Push when ready:"
echo "  git push origin arena/01a02b25-arena-agent"
