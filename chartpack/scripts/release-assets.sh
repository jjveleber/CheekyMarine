#!/usr/bin/env bash
# Usage: release-assets.sh TAG
# Prints the asset names of release TAG in $GITHUB_REPOSITORY, one per line, and exits 0. Exits 3 when the
# release does not exist (HTTP 404) and 1 on any other failure, so an API error is never read as "no release".
set -euo pipefail

if [ $# -ne 1 ]; then
    echo "usage: $0 TAG" >&2
    exit 2
fi

err="$(mktemp)"
trap '[ -n "$err" ] && rm -f -- "$err"' EXIT
if out="$(gh api "repos/${GITHUB_REPOSITORY}/releases/tags/$1" --jq '.assets[].name' 2>"$err")"; then
    if [ -n "$out" ]; then
        printf '%s\n' "$out"
    fi
    exit 0
fi
if grep -q 'HTTP 404' "$err"; then
    exit 3
fi
cat "$err" >&2
exit 1
