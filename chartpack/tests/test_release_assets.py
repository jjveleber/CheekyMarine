import os
import subprocess

import pytest

FAKE_GH = """#!/usr/bin/env bash
# Stand-in for gh: records its arguments, then acts as GH_FAKE says. The release lookup by tag gives id 123;
# the assets endpoint has two pages, and only --paginate returns both.
echo "$@" >> "$GH_FAKE_LOG"
case "$GH_FAKE" in
  missing) echo 'gh: Not Found (HTTP 404)' >&2; exit 1 ;;
  error) echo 'gh: Server Error (HTTP 502)' >&2; exit 1 ;;
  offline) echo 'error connecting to api.github.com' >&2; exit 1 ;;
esac
case "$*" in
  *releases/tags/*) echo 123 ;;
  *--paginate*releases/123/assets*) printf 'nonna10-x.tif\\nfetch-stats-x.json\\ncoast-y.geojson.gz\\n' ;;
  *releases/123/assets*) printf 'nonna10-x.tif\\nfetch-stats-x.json\\n' ;;
  *) echo "unexpected: $*" >&2; exit 1 ;;
esac
if [ "$GH_FAKE" = "assets-error" ] && [[ "$*" == *assets* ]]; then exit 1; fi
"""


@pytest.mark.parametrize("mode, code, out", [
    ("found", 0, "nonna10-x.tif\nfetch-stats-x.json\ncoast-y.geojson.gz\n"),  # both pages
    ("assets-error", 1, ""),
    ("missing", 3, ""),
    ("error", 1, ""),
    ("offline", 1, ""),
])
def test_release_assets_tells_not_found_from_failure(tmp_path, chartpack_dir, mode, code, out):
    """Exit 0 with the asset names, 3 when the release does not exist (HTTP 404), 1 on any other failure, so an
    API error is never read as "no release"."""
    gh = tmp_path / "bin" / "gh"
    gh.parent.mkdir()
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    log = tmp_path / "gh.log"
    env = {**os.environ, "PATH": f"{gh.parent}:{os.environ['PATH']}", "GH_FAKE": mode, "GH_FAKE_LOG": str(log),
           "GITHUB_REPOSITORY": "owner/repo"}
    r = subprocess.run([chartpack_dir / "scripts/release-assets.sh", "sources-bc-1"], capture_output=True, text=True,
                       env=env)
    assert (r.returncode, r.stdout) == (code, out), r.stderr
    calls = log.read_text().splitlines()
    assert calls[0].split()[:2] == ["api", "repos/owner/repo/releases/tags/sources-bc-1"]
    if mode in ("found", "assets-error"):
        assert "--paginate" in calls[1].split() and "repos/owner/repo/releases/123/assets" in calls[1].split()
