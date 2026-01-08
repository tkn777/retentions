### NEXT VERSION
- Added '--fail-on-delete-error'

### 1.0.4 - 05.01.2026
- Fixed bash and zsh completions

### 1.0.3 - 03.01.2026
- Removed generation of shell-completion und used manual created completion files

### 1.0.2 - 03.01.2026
- Fixed test to be more robust again its time of execution
- Optimized README.md for SEO
- Fixed and generalize error handling for validation (parser)
- Omit printing duplicate version on --version
- Cleanup and beautify --help output
- Added test for error handling for validation (parsing) and extend existing test for invalid arguments
- Revised DESIGN_DECISIONS.md and moved to root
- Added RELEASE_POLICY.md

### 1.0.1 - 02.01.2026
- Fixed error handling for max-age and max-size parsing (and validation overall)

### 1.0.0 - 02.01.2026 (initial production release)
- Added `--week13`
- Added templates for issues, pr's
- Activated dependabot
- Added hint regarding atomic operations
- Use ModernStrictArgParser  
  - avoid duplicated (like `-w 5` `--weeks 3`)  
  - suggest in case of argument typos (very simple)  
  - better error display  
  - better usage display  
- Add `--max-size / -s`  
- Add `--max-age / -i`  
- Add and implement `--regex-mode case / ignorecase` for `file_pattern`  
  - Rename `--regex` to `--regex-mode`  
- Add `--max-files / -f`  
- Add `--age-type`: `mtime` (default), `ctime`, `atime`  
- Refactor `main` method  
  - Use `ConfigNamespace` instead of `argparse.Namespace`  
- Use `age-type` (cached)  
- Add `--protect / -p` with glob or regex (same as selected for `file_pattern`)  
- Implement `protect`  
- Implement filter  
  - `max-size`  
  - `max-file`  
  - `max-age`  
- Implement locking  
- Fix max-age, relative to now  
- Implement message history per file  
  - Add skip message to that history (but after current message)  
  - Add everything else file-related to this history  
  - Rename to_(keep|prune) to keep|prune and keep_prune_decisions to log  
  - Use new method def insert_log(..., pos=0)  
  - verbose only first list element for INFO, anything else for debug "└── "  
- Cleanup code  
  - Remove redundancies  
  - Unify function signatures  
  - Use dataclass for retention results  
- Refactored code. - Used classes for  
  - FileStatsCache  
  - Logger  
  - Retention Logic  
- Fix Problem `-a 3 y`  
- Update README.md  
- Split lint and test workflows  
- Create shell-completions in build workflow  
- Update release workflow  
  - Add release artifacts to body  
  - Add changelog to body  
  - Add pure script  
- Review by ChatGPT (5.2, extended thinking)
- Create man page by ChatGPT (and edit manually later)  
- Add comprehensive test suite (coverage >= 80%)
- Add coverage badge

### 0.5.0-beta1 - 16.11.2025 (test release)
- Fixed bash shell completion path

### 0.5.0-beta0 - 16.11.2025 (test release)
- Pre-release (initial release)
