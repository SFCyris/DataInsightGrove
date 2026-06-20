# Release packaging

Builds the downloadable DataInsightGrove release archive — a clean, runnable
source bundle (exactly the tracked files; no `.git`, `node_modules`, `.venv`,
`data/`, build output, or internal working folders). A recipient unzips it and
runs `./install.sh`, the same as a fresh clone.

## Build

```bash
make package                 # package the current HEAD
# or, directly:
./installer/package.sh             # current HEAD
./installer/package.sh v1.0.0      # a specific tag / ref
./installer/package.sh --version 1.2.3   # override the embedded version label
```

Output lands in `installer/dist/` (git-ignored):

| File | Purpose |
|---|---|
| `datainsightgrove-<version>.zip` | versioned artifact, for archival |
| `datainsightgrove-latest.zip` | stable name for the "latest" download link |

The script prints each archive's size and SHA-256.

## Release

1. Commit and tag the release: `git tag v1.0.0`
2. Build from the tag: `./installer/package.sh v1.0.0`
3. Create a GitHub release for the tag and attach **both** zips.

Keep the `datainsightgrove-latest.zip` asset name stable — the README's download
button points at `releases/latest/download/datainsightgrove-latest.zip`, which
always resolves to that asset in the most recent release.

> Note: the archive reflects a committed ref. Packaging `HEAD` with uncommitted
> changes warns and excludes them — commit or tag first.
