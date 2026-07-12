#!/bin/bash
# Check for secrets, API keys, endpoint URLs, and internal model names in the client bundle

set -euo pipefail

BUNDLE_DIR="${1:-dist}"

if [ ! -d "$BUNDLE_DIR" ]; then
  echo "Build directory $BUNDLE_DIR not found. Run 'npm run build' first."
  exit 1
fi

echo "Checking client bundle for leaked secrets..."

FAILED=0

# Patterns that must NOT appear in the client bundle
PATTERNS=(
  "api.llm.ustc.edu.cn"
  "USTC_API"
  "deepseek-v4"
  "qwen3.6"
  "glm-5"
  "sk-[A-Za-z0-9]"
  "bearer"
  "TEACHER_PASSWORD"
  "SESSION_SECRET"
  "SANDBOX_API_KEY"
)

for pattern in "${PATTERNS[@]}"; do
  MATCHES=$(grep -rl "$pattern" "$BUNDLE_DIR/static" 2>/dev/null || true)
  if [ -n "$MATCHES" ]; then
    echo "FAIL: Pattern '$pattern' found in client bundle:"
    echo "$MATCHES" | while read -r file; do
      echo "  $file: $(grep -o "$pattern" "$file" | head -3)"
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