#!/usr/bin/env bash
set -euo pipefail

KB_ROOT="${KB_ROOT:-/Users/liwei/Desktop/on_my_knowledge}"
PRODUCT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 "$KB_ROOT/_tools/renal_treatment_query/build_treatment_index.py"
python3 "$KB_ROOT/_tools/renal_treatment_query/build_public_release.py" --compiled-dir "$KB_ROOT/_tools/renal_treatment_query/compiled" --release-dir "$PRODUCT_ROOT" --force

echo "Updated public release data in: $PRODUCT_ROOT/compiled_public"
echo "Next: upload compiled_public/*.json to OSS, then redeploy/restart Render."
