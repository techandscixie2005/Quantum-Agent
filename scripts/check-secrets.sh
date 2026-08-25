#!/bin/bash
# Check for secrets, API keys, endpoint URLs, and internal model names in the client bundle

set -euo pipefail

BUNDLE_DIR="${1:-dist}"
CLIENT_DIR="${BUNDLE_DIR}/client"

if [ ! -d "$CLIENT_DIR" ]; then
  echo "Client build directory $CLIENT_DIR not found. Run 'npm run build' first."
  exit 1
fi

echo "Checking client bundle for leaked secrets..."

FAILED=0

# Patterns that must NOT appear in the client bundle
PATTERNS=(
  "api\\.llm\\.ustc\\.edu\\.cn"
  "USTC_API"
  "deepseek-v[0-9]"
  "qwen([0-9.]+)?-(chat|reasoner|embedding|reranker)"
  "glm-[0-9]"
  "sk-[A-Za-z0-9_-]{16,}"
  "[Bb]earer[[:space:]]+[A-Za-z0-9._~-]{16,}"
  "TEACHER_PASSWORD"
  "SESSION_SECRET"
  "SANDBOX_API_KEY"
)

mapfile -d '' CLIENT_FILES < <(
  find "$CLIENT_DIR" -type f \
    \( -name '*.js' -o -name '*.mjs' -o -name '*.cjs' -o -name '*.css' \
       -o -name '*.html' -o -name '*.json' -o -name '*.map' -o -name '*.txt' \) \
    -print0
)

if [ "${#CLIENT_FILES[@]}" -eq 0 ]; then
  echo "No text client artifacts found under $CLIENT_DIR; refusing a vacuous pass."
  exit 1
fi

for pattern in "${PATTERNS[@]}"; do
  MATCHES=$(grep -IlE "$pattern" "${CLIENT_FILES[@]}" 2>/dev/null || true)
  if [ -n "$MATCHES" ]; then
    echo "FAIL: Pattern '$pattern' found in client bundle:"
    echo "$MATCHES" | while read -r file; do
      echo "  $file"
    done
    FAILED=1
  else
    echo "PASS: '$pattern' not found in client bundle"
  fi
done

if [ "$FAILED" -eq 1 ]; then
  echo ""
  echo "Secret detection FAILED. Remove sensitive patterns from client-visible code."
  exit 1
else
  echo ""
  echo "Secret detection PASSED. No sensitive patterns found in client bundle."
fi
