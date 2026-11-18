# Examples

Practical examples for [retentions](README.md). Use `--dry-run` first to review planned deletions.

## Retentions & Filters

```bash
# Retain last 7 days, 4 weeks, 6 months
python3 retentions.py /data/backups '*.tar.gz' -d 7 -w 4 -m 6
```

```bash
# Keep daily/weekly/monthly backups, but retain at most 10 files in total.
# Older retained files are deleted if the limit is exceeded.
python3 retentions.py /data/backups '*.tar.gz' -d 7 -w 4 -m 6 --max-files 10 --dry-run
```

```bash
# Keep up to 12 monthly backups, but limit total retained size to 50 GB.
# Older retained files are deleted once the size limit is exceeded.
python3 retentions.py /data/backups '*.tar.gz' -m 12 --max-size 50G --dry-run
```

## Dry run (no deletion)

```bash
python3 retentions.py /data/backups '*.tar.gz' -d 10 -w 3 -m 6 --dry-run
```

## List-only mode (for piping into other tools)

```bash
python3 retentions.py /data/backups '*.tar.gz' -d 5 -w 12 --list-only '\0' | xargs -0 rm
```
⚠️ This bypasses retentions' own deletion **safety mechanisms**. Use with care!

## Verbose output

```bash
# Detailed logging
python3 retentions.py /data/backups '*.tar.gz' -d 3 -w 1 --verbose debug
```

## Protecting a single file

Keep the three newest unprotected files and leave `.important` untouched. Other hidden files, such as `.not-important`, are processed normally.

```bash
retentions /data/backups '*' --last 3 --protect '.important' --dry-run
```

## Limiting retention by age

Retain up to ten backups, with a maximum age of 30 days.

```bash
retentions /data/backups '*.tar.gz' --last 10 --max-age 30d --dry-run
```

## Folder mode

Use `time.txt` inside each backup folder as its timestamp source and keep the three newest folders. Each folder being processed must contain that file.

```bash
retentions /data/backups '*' --folder-mode 'path=time.txt' --last 3 --dry-run
```

## Skipping small files

Keep the seven newest matching backups that are at least 1 MiB (1,048,576 bytes). Smaller files are marked for deletion.

```bash
retentions /data/backups '*.tar.gz' --last 7 --skip-by-filesize 1M --dry-run
```

## Folder time source with an equals sign

If the time file is named `stamp=done.txt`, escape the `=` in its name:

```bash
retentions /data/backups '*' --folder-mode 'path=stamp\=done.txt' --last 7 --dry-run
```

## Filename timestamps

```bash
retentions /data/backups 'backup-*.tar.gz' --age-type 'filename=%Y-%m-%d' --days 7 --dry-run
```

## Symbolic links

```bash
retentions /data/backups '*.tar.gz' --last 7 --delete-symlinks directory --dry-run
retentions /data/backups '*.tar.gz' --last 7 --delete-companions 'suffix:.tar.gz:.sha256' --delete-symlinks system --dry-run
```

## 🗓️ Hierarchical calendar-based retention example

Retention levels are applied hierarchically by calendar containment, not additively by age.

Each coarser-grained retention level only selects data strictly *outside* the
calendar range already covered by finer-grained levels.

Example:

```
-d 1 -w 1 -m 1
```

Assume the most recent retained day is: `2026-01-31`

This day lies in:
- calendar week **2026-W05**
- calendar month **2026-01**

Retention selection therefore proceeds as follows:

- **Days (`-d 1`)**
  - keep: `2026-01-31`

- **Weeks (`-w 1`)**
  - select a week *before* calendar week `2026-W05`
  - the week containing the retained day is excluded
  - the first eligible week is **2026-W04**

- **Months (`-m 1`)**
  - select a month *before* calendar month `2026-01`
  - the month containing the retained week is excluded
  - the first eligible month is **2025-12**

If no data exists in these older calendar buckets, no additional items are kept.

This hierarchical approach ensures that:
- finer-grained retention always takes precedence,
- coarser-grained retention never overlaps with finer levels,
- and each retention level contributes unique temporal coverage.
&nbsp;

```text
Time ──────────────────────────────────────────────────────────────▶

Month:   2025-12        |        2026-01
         [ eligible ]   | [ excluded by weeks ]
                         ┌──────────────────────-─────────┐
Week:                    │   2026-W05  (excluded)         │
                         │   2026-W04  ← selected (weeks) │
                         └─────────────────────-──────────┘
Day:                                   2026-01-31 ← selected (days)
```
