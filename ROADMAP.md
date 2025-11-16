## 1.0
- Implement `--size-total / -s`
- Implement `--within / -i`
- Implement `--protect / -p` with glob or regex (same as selected for `pattern`)
- Implement `--regex-mode case / ignorecase` for `pattern` and `--protect`
  - Rename `--regex` to `--regex-mode`
- Implement `--files-total`
- Implement `--folders-mode / -f`: `age-mode` (of folder, default), latest (by `age-mode`), oldest (`by age-mode`)
- Implement `--age-type`: mtime (default), ctime, atime
- Implement `--confirm-delete / -C`
- Implement message (verbose) history per file (output for `--verbose 3` only)
- ~~Refactor main method~~
  - Use dict instead of argparse.Namespace
- Add comprehensive test suite (coverage >= 80%)
- Add coverage badge
- Stabilize and test by others
- Templates for issues
- Add hint regarding atomic operations => filesystems are not atomic

Logic
1. Time-based retentions (--hours, --days, --weeks, --months, --years, --quarter, --week13)
2. Added by --last (latest N files within the allowed window)
3. Filtered by --within (strict time cutoff)
4. Filtered by --files-total (upper limit by count)
5. Filtered by --size-total (upper limit by total storage)
6. Protected by --protect (absolute priority; never deleted)

## Later
- Show cases
- Debian package = valid Debian package with positive linting
  - control
  - copyright
  - ...
