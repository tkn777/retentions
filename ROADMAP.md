## 1.0
- Use StrictArgParser ✓
  - avoid duplicated (like `-w 5` `--weeks 3`) ✓
  - suggest in case of argument typos (very simple) ✓
  - better error display ✓
  - better usage display ✓
- Add `--max-size / -s` ✓
- Add `--max-age / -i` ✓
- Add and implement `--regex-mode case / ignorecase` for `file_pattern` ✓
  - Rename `--regex` to `--regex-mode` ✓
- Add `--max-files / -f` ✓
- Add `--age-type`: `mtime` (default), `ctime`, `atime` ✓
- Refactor `main` method ✓
  - Use `ConfigNamespace` instead of `argparse.Namespace` ✓
- Use `age-type` (cached) ✓
- Add `--protect / -p` with glob or regex (same as selected for `file_pattern`) ✓
- Implement `protect` ✓
- Implement filter ✓
  - `max-size` ✓
  - `max-file` ✓
  - `max-age` ✓
- Implement locking ✓
- Fix max-age, relative to now ✓
- Implement message history per file
  - Add skip message to that history (but after current message)
  - Add everything else file-related to this history
  - Use type alias
  - Rename to_(keep|prune) to keep|prune and keep_prune_decisions to log
  - Use new method def insert_log(..., pos=0)
  - verbose only first list element for INFO, anything else for debug "└── "
- Cleanup code ✓
  - Remove redundancies ✓
  - Unify function signatures ✓
  - Use dataclass for retention results ✓
- Fix Problem `-a 3 y` ✓
- Update README.md
- Review by ChatGPT
- Split lint and test workflows ✓
- Create shell-completions in build workflow ✓
- Update release workflow ✓
  - Add release artifacts to body ✓
  - Add changelog to body ✓
  - Add pure script ✓
- Create man page by ChatGPT (and edit manually later)
- Add comprehensive test suite (coverage >= 80%), with support by ChatGPT
- Add coverage badge


### Logic
1. Scan all files
2. Ignore all protected files (for the whole process)
3. Added by time-based buckets (--hours, --days, --weeks, --months, --years, --quarter, --week13)
4. Added by --last (latest N files)
5. Filtered by 
    1. --max-age (strict time cutoff)
    2. --max-files (upper limit by file count)
    3. --max-size (upper limit by total storage)
6. Delete files or list files to delete

---

## 1.1
- Stabilize and test by others

---

## 1.2
- Implement `--folder / -f`: `age-type` (of folder, default), latest (by `age-type`), oldest (`by age-type`)
    - Implement `--file` (current default to co-existent with folder)
- Implement `--confirm-delete / -c` (for tty's)
- Implement `--delete-companions / -o`
- Implement `--last-within / -i`
- Implement `--fail-on-delete-error`

---

## 1.3
- Cache for `get_file_attributes()`

---

## LATER (may be)
- Use colors
- Show cases
- Debian package = valid Debian package with positive linting
  - control
  - copyright
  - ...
