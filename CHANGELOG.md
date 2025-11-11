### 0.3.2 - 11.11.2025
- Fixed verbose regarding latest

### 0.3.1 - 11.11.2025
- Fixed bug regarding `--last` (verbose does not always fit, but functionally it is correct)

### 0.3.0 - 11.11.2025
- **BREAKING CHANGE**: An exception while deleting a file does not terminate the programm, just print an error message.
- **BREAKING CHANGE**: Use `-H` (or `--help`) for help  and `-h` (or `--hours`) for hours to keep
- **BREAKING CHANGE**: `--verbose` (or `-V`) takes an int argument as log level (Verbosity level: 0 = silent, 1 = deletions only, 2 = detailed output)
- **BREAKING CHANGE**: If no retention options are specified, an error is raise (before: `--last=10` was used as default)
- Added `--quarters` (or `-Q`) option to keep the last `N` qarters
- Added security checks
- Fix some argument handling
- Improved output of verbose
- Added CI workflow for linting and simple test
- Added `SECURITY.md` and `CONTRIBUTING.md`

### 0.2.0 - 09.11.2025
- **BREAKING CHANGE**: Added `--regex` option to explicit define type of pattern (default type of pattern is glob)
- Added value to `--list-only` to be used as a separator between listed files (e.g. to be use with `xargs -0`)
- Optimized verbose output: Added details like key, mtime - and printing not-kept files with same details
- Extract config to `pyproject.toml`

### 0.1.0 - 09.11.2025
- Initial release
