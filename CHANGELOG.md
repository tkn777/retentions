### 0.3.0 - 11.11.2025
- **BREAKING CHANGE**: An exception while deleting a file does not terminate the programm, just print an error message.

### 0.2.0 - 09.11.2025
- **BREAKING CHANGE**: Added `--regex` option to explicit define type of pattern (default type of pattern is glob)
- Added value to `--list-only` to be used as a separator between listed files (e.g. to be use with `xargs -0`)
- Optimized verbose output: Added details like key, mtime - and printing not-kept files with same details
- Extract config to `pyproject.toml`

### 0.1.0 - 09.11.2025
- Initial release