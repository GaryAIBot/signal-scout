#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="/home/ubuntu/.config/gary/vercel-secrets.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi
set -a
source "$ENV_FILE"
set +a
for name in OPENAI_API_KEY GOOGLE_API_KEY; do
  value="${!name:-}"
  if [[ -z "$value" ]]; then
    echo "Skipping empty $name" >&2
    continue
  fi
  for env in production preview development; do
    printf "%s" "$value" | vercel env add "$name" "$env" --force
  done
done
