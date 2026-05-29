#!/usr/bin/env bash
# Build sdist + wheel locally, after running the conformance test gate.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Installing package (editable) + build tools"
python -m pip install -e . build >/dev/null

echo "==> Running conformance tests"
python -m unittest discover -s tests -p "test_*.py" -v

echo "==> Validating golden fixture"
python conformance/validate_report.py conformance/golden_report.xml

echo "==> Building sdist + wheel"
rm -rf dist build ./*.egg-info
python -m build

echo "==> Done. Artifacts:"
ls -1 dist/
