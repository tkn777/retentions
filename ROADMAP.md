## 1.0
- Implement `--size-total / -s`
- Implement `--within / -i`
- Implement `--week13`
- Implement `--protect / -p` with glob or regex (same as selected for pattern)
- Implement `--regex case / nocase` for pattern and `--protect`
- Implement `--files-total`
- Implement `--folders / -f`: age-mode (of folder, default), latest (by age-mode), oldest (by age-mode)
- Implement `--age-mode`: mtime (default), ctime, atime
- Implement `--confirm-delete / -C`
- Implement message (verbose) history per file
- Refactor main method
- Add verbose function
- Add comprehensive test suite (coverage >= 80%)
- Add coverage badge
- Stabilize and test by others
- Templates for issues
- Template for PR
- Dependabot for python dev deps and github actions

## Later
- Show cases
- Debian package = (valid Debian package with positive linting)
  - control
  - copyright
  - ...
