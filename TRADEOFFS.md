# Known Issues & Trade-offs

The following behaviors are known, intentional trade-offs rather than bugs.

- **Symlink search scope:** `--delete-symlinks directory` has depth 0 and does not follow directory symlinks. `system` follows directory symlinks recursively from `/`. On Windows, it starts at the root of the current drive; other drives and network shares are not enumerated, but can be reached through directory symlinks. The top-level directories `dev`, `proc`, `sys` and `run` are excluded from the system search, including when reached through directory symlinks.

- **Symlink search cost and completeness:** A system search can take a long time on large or network filesystems. It runs during file discovery, even if retention later keeps all files. Inaccessible areas and unresolvable or cyclic links can be skipped silently. Concurrent filesystem changes can also prevent complete cleanup. The option does not guarantee removal of every link on the system; symlink support and access depend on the platform, filesystem and permissions.

- **Filter time intervals (`--max-age`):** The retention options `--months`, `--quarters` and `--years` use calendar buckets, while `--max-age` uses fixed durations:
  - `xm` => x * 30 days
  - `xq` => x * 90 days
  - `xy` => x * 365 days

- **Extremely large age limits:** Numeric `--max-age` values that overflow the floating-point representation, either directly or after unit conversion, are accepted as an infinite age limit. The age filter then leaves all retained files unchanged; other retention rules and filters still apply. Explicit finite-value validation is intentionally omitted for this extreme input range.

- **Companion protection checks after main-file deletion:** Main-file deletion precedes companion checks and deletion. Protected or otherwise disallowed companions (e.g. files marked as kept or pruned) abort the run with exit code 7. The main file and any companions already deleted remain deleted; no rollback is performed.

- **Explicit option names:** Long options must be spelled out; only explicitly defined aliases are accepted. For example, `--days` and `-d` are valid, while `--day` is rejected with exit code 2. This avoids implicit spellings that bypass duplicate-option checks. Scripts using abbreviated long options must switch to full names or supported aliases.

- **Separate short options:** Combined short options such as `-Xm2`, `-Xd1` and `-XL` are rejected with exit code 2. Pass options separately, for example `-X -m 2` or `-X -m2`. Single options with attached values, such as `-m2` and `-d1`, remain valid. This keeps option handling explicit and prevents combinations from bypassing duplicate-option checks.

## Non-atomic behavior

retentions does not operate atomically. Since the underlying filesystem is not atomic, directory contents may change while retentions is scanning or evaluating files.
This can lead to inconsistent or incorrect results if the target path is modified concurrently.
If you require a strictly consistent state, ensure that the directory is not modified during execution.

By default retentions writes a lock file `.retentions.lock` - This can be used by other tools.
