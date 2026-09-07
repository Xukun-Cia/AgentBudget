#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  forbidden="$({ git -C "$ROOT" ls-files || true; } | grep -Ei '(^|/)(auth\.json|probe-results\.json|api-response\.json|.*\.vscdb(-wal|-shm)?|\.env)$' || true)"
  if [[ -n "$forbidden" ]]; then
    echo "Privacy check failed: a private dump or credential file is tracked." >&2
    echo "$forbidden" >&2
    exit 1
  fi

  secret_files="$({
    git -C "$ROOT" grep -IlE 'sk-[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]{16,}\.eyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}' -- . \
      ':(exclude)scripts/check-privacy.sh' || true
  } | sort -u)"
  if [[ -n "$secret_files" ]]; then
    echo "Privacy check failed: a tracked file resembles a live credential." >&2
    echo "$secret_files" >&2
    exit 1
  fi
fi

private_files="$(find "$ROOT" \
  -path "$ROOT/.git" -prune -o \
  -path "$ROOT/dist" -prune -o \
  -path "$ROOT/.agents" -prune -o \
  -path "$ROOT/.codex" -prune -o \
  -type f \( -name 'auth.json' -o -name 'probe-results.json' -o \
    -name 'api-response.json' -o -name '*.vscdb' -o -name '*.vscdb-wal' -o \
    -name '*.vscdb-shm' -o -name '.env' -o -name '.env.*' \) -print)"
if [[ -n "$private_files" ]]; then
  echo "Privacy check failed: a private local file exists inside the project." >&2
  echo "$private_files" >&2
  exit 1
fi

working_secret_files="$({
  grep -RIlE \
    --exclude-dir=.git --exclude-dir=dist --exclude-dir=.agents --exclude-dir=.codex \
    --exclude=check-privacy.sh \
    'sk-[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]{16,}\.eyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}' \
    "$ROOT" || true
} | sort -u)"
if [[ -n "$working_secret_files" ]]; then
  echo "Privacy check failed: a project file resembles a live credential." >&2
  echo "$working_secret_files" >&2
  exit 1
fi

echo "Privacy check passed: no credential files or token-shaped values are present in the project."
