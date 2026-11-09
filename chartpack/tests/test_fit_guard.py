import json
import os
import stat
import subprocess

import pytest

GIB_KB = 1024 * 1024


@pytest.fixture
def guard(chartpack_dir, tmp_path):
    """Run fit-guard.sh with a fake time (prints a chosen RSS) and a fake df (scripted free values)."""
    fake_time = tmp_path / "faketime"
    fake_time.write_text(
        "#!/usr/bin/env bash\n"
        '# usage: faketime -v -o FILE CMD...\n'
        'shift; shift; out="$1"; shift\n'
        '"$@"; rc=$?\n'
        'echo "\\tMaximum resident set size (kbytes): ${FAKE_RSS_KB:-1000}" > "$out"\n'
        'exit $rc\n'
    )
    fake_df = tmp_path / "fakedf"
    fake_df.write_text(
        "#!/usr/bin/env bash\n"
        '# Free values come from FAKE_DF_SEQ (space separated, last one repeats), one per call.\n'
        'n=$(cat "$FAKE_DF_STATE" 2>/dev/null || echo 0); echo $((n + 1)) > "$FAKE_DF_STATE"\n'
        'read -r -a seq <<< "$FAKE_DF_SEQ"\n'
        'i=$n; [ "$i" -ge "${#seq[@]}" ] && i=$((${#seq[@]} - 1))\n'
        'echo "Filesystem 1K-blocks Used Available Use% Mounted on"\n'
        'echo "fake 99999999 1 ${seq[$i]} 1% /"\n'
    )
    for f in (fake_time, fake_df):
        f.chmod(f.stat().st_mode | stat.S_IEXEC)

    def run(*cmd, rss_kb=1000, df_seq="9000000", sample_s="0.1"):
        out = tmp_path / "stats.json"
        env = dict(
            os.environ,
            CM_TIME=str(fake_time),
            CM_DF=str(fake_df),
            CM_SAMPLE_S=sample_s,
            CM_WORK=str(tmp_path),
            FAKE_RSS_KB=str(rss_kb),
            FAKE_DF_SEQ=df_seq,
            FAKE_DF_STATE=str(tmp_path / "df-state"),
        )
        r = subprocess.run(
            [chartpack_dir / "scripts/fit-guard.sh", out, "--", *cmd],
            capture_output=True, text=True, env=env,
        )
        stats = json.loads(out.read_text()) if out.exists() else None
        return r, stats

    return run


def test_passes_and_writes_stats(guard):
    r, stats = guard("true", rss_kb=2 * GIB_KB, df_seq="9000000 8000000 8500000")
    assert r.returncode == 0, r.stderr
    assert stats["max_rss_kb"] == 2 * GIB_KB
    assert stats["min_disk_free_kb"] == 8000000
    assert stats["elapsed_s"] >= 0


def test_rss_over_limit_fails(guard):
    r, stats = guard("true", rss_kb=12582912 + 1)
    assert r.returncode == 1
    assert "runner fit: max RSS over the limit" in r.stderr
    assert stats["max_rss_kb"] == 12582912 + 1


def test_low_disk_during_run_fails(guard):
    # Free space dips under 2 GiB mid-run, then recovers before the command ends.
    r, stats = guard("sleep", "1", df_seq="9000000 9000000 1000000 9000000")
    assert r.returncode == 1
    assert "runner fit: disk use over the limit" in r.stderr
    assert stats["min_disk_free_kb"] == 1000000


def test_command_failure_passes_through(guard):
    r, stats = guard("sh", "-c", "exit 7")
    assert r.returncode == 7
    assert stats is not None


def test_returns_promptly_with_long_sample_interval(guard):
    # An orphaned sleep would hold the captured pipes open for the full 30 s.
    import time
    t0 = time.monotonic()
    r, _ = guard("true", sample_s="30")
    assert r.returncode == 0
    assert time.monotonic() - t0 < 10
