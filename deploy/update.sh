#!/usr/bin/env bash
# Rebuild the graph from fresh Scryfall data and reload the QLever endpoint.
# Run by managraph-update.timer weekly, or by hand: bash deploy/update.sh
#
# The pipeline fails on SHACL violations; with set -e that stops here and the
# endpoint keeps serving the previous index.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$HOME/.local/bin:$PATH"
QLEVER=(uvx --python 3.12 qlever)
TOKEN="$(cat "$HOME/.managraph-token")"

cd "$DIR"
git pull --ff-only
uv sync --locked
uv run managraph

cd qlever
"${QLEVER[@]}" stop || true
"${QLEVER[@]}" index --overwrite-existing
# Smaller limits than the Qleverfile's: plenty for ManaGraph's size, and they
# leave room for the next rebuild on a 12 GB server.
"${QLEVER[@]}" start --access-token "$TOKEN" --restart-policy unless-stopped \
  --memory-for-queries 2G --cache-max-size 1G
