# CheekyMarine installer

## Lock format (contract)

`cheekymarine.lock` pins one matched set of parts. It is a flat `key=value` text file: no sections,
`#` comments, one key per line. Bash reads it with no extra tool, and the plotter reads it as an
INI file through `QSettings`. The installer embeds it in `cheekymarine.sh`, and the plotter and
the later self-updater read the same file, so this format is a contract.

Keys, in this order:

| Key | Meaning |
| --- | --- |
| `schema` | Lock format number. Bumps on an incompatible change. Currently `1`. |
| `set` | Set version `X.Y.Z`. |
| `<part>.version` | Version of the part (`n2kd`, `charts`, `bathy`, `plotter`). |
| `<part>.tag` | GitHub release tag that holds the part's asset. |
| `<part>.asset` | Asset file name in that release. |
| `<part>.sha256` | SHA-256 of the asset, as listed in the release's `SHA256SUMS`. |
| `charts.schema`, `bathy.schema` | The pack's manifest `schema`. Placed after the pack's `sha256`. They exist so a later project can update packs apart from sets. |
| `plotter.pack_schema_min`, `plotter.pack_schema_max` | Inclusive range of pack manifest `schema` values the set's plotter accepts. Placed after the plotter's `sha256`. |

Rules for readers:

- Ignore keys you do not know. New keys may appear without a `schema` bump.
- `schema` bumps only on an incompatible change (a key removed or its meaning changed).
- A `sha256` of 64 zeros means the part is not released yet.

## lock-tool.sh

- `lock-tool.sh check LOCK`: exit 0 when every part's `sha256` equals the line for its `asset` in
  `<base>/<tag>/SHA256SUMS` and each pack's `schema` is inside the plotter range. Otherwise exit 1,
  naming the part.
- `lock-tool.sh fill LOCK`: rewrite each `sha256` from those files.
- `lock-tool.sh embed LOCK SCRIPT OUT`: write OUT as SCRIPT with the lines between
  `CM_LOCK=$(cat <<'LOCK'` and `LOCK` replaced by the lines of LOCK.

`<base>` is `${CM_BASE_URL:-https://github.com/jjveleber/CheekyMarine/releases/download}`.

## Tests

From the repo root: `python3 -m unittest discover -s installer/tests -v`
