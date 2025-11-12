<p align="left">
  <img src="resources/retentions-logo.png" alt="retentions logo" height=100>
</p>

A tiny, cross-platform CLI tool to apply backup-style retention rules to any file set. 

It keeps only the most recent or representative files according to simple time-based rules and removes the rest.

```bash
retentions /data/backups '*.tar.gz' -d 7 -w 4 -m 6   # Keeps last 7 days, 4 weeks and 6 months
```

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/tkn777/retentions?sort=semver&cacheSeconds=300)](https://github.com/tkn777/retentions/releases)
[![Platform](https://img.shields.io/badge/platform-linux%20|%20macos%20|%20windows-lightgrey)]()

---

## 🌐 Overview  

`retentions` is a single-file Python script that applies retention logic to a directory of files. 

It groups files into time **buckets** (hours, days, weeks, months, quarters, years) and keeps only one representative file per bucket, typically the most recent one.  

Everything outside your defined retention scope is deleted (unless `--dry-run` or `--list-only` is used).

⚠️ **Warning:** This tool permanently deletes files outside the defined retention scope.  
Use `--dry-run` first to verify behavior. The author assumes no liability for data loss.

---

## ⚙️ Features

- Pure **Python 3**, no external dependencies.  
- Runs on **Linux, macOS, and Windows** (and anywhere else Python 3 runs).  
- Supports **hourly, daily, weekly, monthly, quarterly and yearly** retention buckets.  
- Supports **keeping the last N files** (`--last`) regardless of age.  
- Supports **regex or glob** pattern matching.  
- Safe modes:  
  - `--dry-run` → simulate actions  
  - `--list-only` → output only files that would be deleted  
- Usage:
  - `--help` (also described below in this document)
- Version:
  - `--version`
- Clean, deterministic output - ASCII only, no colors, no locales.

---

## 🧠 Logic Summary

1. **Collect all matching files** under the given path.  
2. **Sort** them by modification time (newest first).  
3. **Keep**:
   - Newest file per retention period (cumulative): `hour` / `day` / `week` / `month` / `quarter` / `year`
   - Last `N` files (`--last`) (regardless from other retention periods)
4. **Delete** everything else.  
5. If `--dry-run` is enabled, print the planned actions instead of executing them.

---

## 🧰 Installation

You can install **retentions** in several ways, depending on your system and preference.

### 🧩 Option 1 – Debian Package (.deb)

Download the latest `.deb` package from the [Releases](https://github.com/tkn777/retentions/releases) page and install it manually:

```bash
sudo dpkg -i retentions_x.y.z.deb
```

This installs:
- `/usr/bin/retentions`
- documentation in `/usr/share/doc/retentions/`

### 📦 Option 2 – Redhat Package (.rpm)

Download the latest `.rpm` package from the [Releases](https://github.com/tkn777/retentions/releases) page and install it manually:

```bash
sudo dnf install retentions-x.y.z-n.noarch.rpm # or with yum
```

This installs:
- `/usr/bin/retentions`
- documentation in `/usr/share/doc/retentions/`

### 🗜️ Option 3 – Universal (tar.gz)

For non-Debian-based or non-Redhat-based systems:

Download the latest `.tar.gz` package from the [Releases](https://github.com/tkn777/retentions/releases) page and install it manually

The archive includes:
- the common Python script: `retentions.py`
- a common linux variant with shebang: `linux/retentions`
- a macOS variant with shebang: `macos/retentions`
- and all the docs: `docs`

### 🔍 To verify installation:

```bash
retentions --help
```

All installation methods require **Python 3.9+**.

No dependencies beyond Python 3.

---

## 🖥️ Usage

```bash
python3 retentions.py [path] [file_pattern] <options>
```

*If you installed via .deb or .rpm or a shebang'ed version from the tar.gz, you can simply run `retentions` instead of `python3 retentions.py`.*

---

## 🔧 Arguments

| Arguments | Description |
|--------|--------------|
| `path` | base directory to scan |
| `file_pattern` | glob pattern for matching files (use quotes to prevent shell expansion) |
| `-r, --regex` | file_pattern is a regex (default: glob pattern) |

⚠️ `path` and `file_pattern` are mandatory\
&nbsp;

| Retention options | Description |
|--------|--------------|
| `-h, --hours <int>` | Keep one file per hour from the last N hours |
| `-d, --days <int>` | Keep one file per day from the last N days |
| `-w, --weeks <int>` | Keep one file per week from the last N weeks |
| `-m, --months <int>` | Keep one file per month from the last N months |
| `-q, --quarters <int>` | Keep one file per quarter from the last N quarters |
| `-y, --years <int>` | Keep one file per year from the last N years |
| `-l, --last <int>` | Always keep the N most recently modified files |

📝 Every retention option can be combined with any (or all) others

🧠 Logic:
- The retention periods are applied cumulatively. For example, a file that is marked as keep with the retention `--days` cannot also be marked as keep with the retention `--week`.
- One exception here is `--last`. It always marks the last `N` files as keep, regardless of all other retentions.

⚠️ At least one retention option has to be specified\
&nbsp;

| Behavior options | Description |
|--------|--------------|
| `-L, --list-only <separator>` | Output only file paths that would be deleted (incompatible with --verbose, separator defaults to '\n') |
| `-V, --verbose <int>` | Verbosity level: 0 = silent, 1 = deletions only, 2 = detailed output (default: 2, if specified without value) |
| `-X, --dry-run` | Show planned actions but do not delete any files |

💡 Using `--dry-run` is a good option to start with `retentions` 😏\
&nbsp;

| Common options | Description |
|--------|--------------|
| `-H, --help` | Show the help / usage of `retentions` |
| `-R, --version` | Show the version of `retentions` |

💡 Common options can be used without any other arguments.

---

### 🧾 Examples

```bash
# Keep last 7 days, 4 weeks, 6 months
python3 retentions.py /data/backups '*.tar.gz' -d 7 -w 4 -m 6
```

#### Dry run (no deletion)

```bash
python3 retentions.py /data/backups '*.tar.gz' -d 10 -w 3 -m 6 --dry-run
```

#### List-only mode (for piping into other tools)

```bash
python3 retentions.py /data/backups '*.tar.gz' -d 5 -w 12 --list-only '\0' | xargs -0 rm
```

#### Verbose output

```bash
# Detailed logging
python3 retentions.py /data/backups '*.tar.gz' -d 3 -w 1 --verbose 2
```

---

### ⚠️ Important – Quoting File Patterns

Always **quote your file patterns** when calling `retentions`.

If you omit the quotes, your shell (e.g. Bash, Zsh, PowerShell) will expand the pattern **before** it reaches the program, resulting in unexpected arguments or errors.

#### ✅ Correct
```bash
python3 retentions.py /data/backups '*.tar.gz'
python3 retentions.py /data/logs 'log-*.txt'
python3 retentions.py /data/temp '.*\\.bak'
```

#### ❌ Incorrect
```bash
python3 retentions.py /data/backups *.tar.gz
```
(your shell expands *.tar.gz before retentions runs)

retentions itself handles pattern matching internally using glob or regex, so quoting ensures the pattern is passed as intended.

--- 

## ⚡ Exit Codes

| Code | Meaning |
|------|----------|
| 0 | Execution successful |
| 1 | I/O or filesystem error |
| 2 | Invalid or conflicting arguments |
| 3 | Pattern matched no files |
| 7 | Integrity check failed |
| 9 | Unexpected error |

---

## 📦 Design Principles

- **KISS** – no configuration files, no hidden behavior.  
- **Deterministic** – same input, same output.  
- **Safe by design** – dry-run and list-only modes available.  
- **Cross-platform** – runs anywhere Python 3 does.  
- **Plain ASCII** – no colors, no locale dependencies.

---

## 💡 Tip

Use `--list-only` to integrate with external scripts or pipelines:

```bash
python3 retentions.py /data/logs '*.log' -d 3 -w 2 --list-only | while read f; do
    echo "Would delete $f"
done
```

---

## 📜 Changelog

See [CHANGELOG.md](CHANGELOG.md) for recent updates.

---

## 💖 Sponsoring

If you find `retentions` useful, consider supporting its future development via PayPal: 

[![Donate via PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/kuhlmannthomas)

Your support helps maintain and improve open-source tools like this one.
Thank you for your generosity!

---

## 🪶 License

MIT License  
Copyright © 2025 Thomas Kuhlmann

---

Simple. Predictable. Cross-platform.  
Just **retentions**.
