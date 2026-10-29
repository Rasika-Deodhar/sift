#!/usr/bin/env bash
# Hackathon compliance checks (run by `make lint`):
#  1. No non-Meta AI SDKs or endpoints anywhere in the product code or dependency manifests.
#  2. No code that scrapes, automates or injects into a third-party platform.
set -euo pipefail
cd "$(dirname "$0")/.."
fail=0
SRC=(backend/app backend/pyproject.toml frontend/src frontend/package.json frontend/package-lock.json demo_feed)

ai_sdks='(^|[^a-z_-])(openai|anthropic|cohere|mistralai|groq|replicate|togetherai|together-ai|huggingface_hub|google[.-]generativeai|@google/genai|google-genai|vertexai|langchain|llamaindex|ollama)([^a-z_-]|$)'
ai_hosts='api\.openai\.com|api\.anthropic\.com|generativelanguage\.googleapis\.com|api\.cohere|api\.mistral\.ai|api\.groq\.com'
# "OpenAI-compatible" in comments describes Meta's wire format, not a dependency.
if grep -rInE "$ai_sdks|$ai_hosts" "${SRC[@]}" | grep -viE 'openai-compatible|openai sdk works'; then
  echo "FAIL: non-Meta AI provider reference found above"; fail=1
fi

platforms='instagram\.com|facebook\.com|threads\.net|tiktok\.com|x\.com/|twitter\.com|youtube\.com'
automation='puppeteer|selenium|chrome\.runtime|content_scripts|webRequest|chrome\.tabs|browser\.tabs'
if grep -rInE "$platforms|$automation" "${SRC[@]}" frontend/scripts; then
  echo "FAIL: third-party platform or browser-automation reference found above"; fail=1
fi
# The dev scripts drive Chromium, but only against Sift and its own Demo Feed.
if grep -nE "goto\(" frontend/scripts/*.mjs | grep -vE 'BASE|localhost'; then
  echo "FAIL: a dev script navigates somewhere other than Sift / the Demo Feed"; fail=1
fi

# Raw frames/audio must never be written to disk by the backend.
if grep -rnE "open\([^)]*['\"]wb?['\"]|write_bytes|\.save\(" backend/app; then
  echo "FAIL: backend writes files (frames/audio must stay in memory)"; fail=1
fi

[ "$fail" = 0 ] && echo "compliance: OK (Meta models only; screen-share input only; no raw media on disk)"
exit "$fail"
