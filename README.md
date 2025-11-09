# retentions

A minimal cross-platform CLI tool for file retention management.  

It keeps only the most recent or representative files according to simple time-based rules and removes the rest.

---

## 🌐 Overview

`retentions` is a single-file Python script that applies retention logic to a directory of files. 

It groups files into time **buckets** (hours, days, weeks, months, years) and keeps only one representative file per bucket, typically the most recent one.  

Everything outside your defined retention scope is deleted (unless `--dry-run` or `--list-only` is used).

⚠️ **This software deletes files. Use at your own risk.**  
**The author assumes no responsibility for data loss or damage.**

---

## ⚙️ Features

- Pure **Python 3**, no external dependencies.  
- Runs on **Linux, macOS, and Windows** (and everywhere else, where python 3 runs).  
- Supports **hourly, daily, weekly, monthly, and yearly** retention buckets.  
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
3. **Retain**:
   - Newest file per `hour` / `day` / `week` / `month` / `year`
   - Last `N` files (`--last`)
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

For non-Debian systems or manual setups:

Download the latest `.tar.gz` package from the [Releases](https://github.com/tkn777/retentions/releases) page and install it manually

It includes
- the common python script: `retentions.py`
- a common linux variant with shebang: `linux/retentions`
- a macos variant with sheban: `macos/retentions`
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
python3 retentions.py [path] [file_pattern] [options]
```

> *Depending on your installation type, you may just call `retentions` instead of `python3 retentions.py` .*

---

## 🔧 Arguments

| Argument | Description |
|--------|--------------|
| `path` | Base directory to scan |
| `file_pattern` | glob pattern for matching files (use quotes to prevent shell expansion) |
| `-r, --regex` | file_pattern is a regex (default: glob pattern) |
| `-H, --hours <int>` | Keep one file per hour from the last N hours |
| `-d, --days <int>` | Keep one file per day from the last N days |
| `-w, --weeks <int>` | Keep one file per week from the last N weeks |
| `-m, --months <int>` | Keep one file per month from the last N months |
| `-y, --years <int>` | Keep one file per year from the last N years |
| `-l, --last <int>` | Always keep the N most recently modified files |
| `-X, --dry-run` | Show planned actions but do not delete any files |
| `-L, --list-only <separator>` | Output only file paths that would be deleted (incompatible with --verbose, separator defaults to '\n') |
| `-V, --verbose` | Show detailed output of KEEP/DELETE decisions and time buckets |

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
python3 retentions.py /data/backups '*.tar.gz' -d 3 -w 1 --verbose
```

---

### ⚠️ Important – Quoting File Patterns

Always **quote your file patterns** when calling `retentions`.

If you omit the quotes, your shell (e.g. Bash, Zsh, PowerShell) will expand the pattern **before** it reaches the program,  
resulting in unexpected arguments or errors.

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
(the shell expands *.tar.gz before retentions runs)

retentions itself handles pattern matching internally using glob or regex,
so quoting ensures the pattern is passed as intended.

---

## 📦 Design Principles

- **KISS** – no configuration files, no hidden behavior.  
- **Deterministic** – same input, same output.  
- **Safe by intention** – dry-run and list-only modes available.  
- **Cross-platform** – works anywhere Python 3 runs.  
- **Plain ASCII** – no colors, no locale dependencies.

---

## 🪶 License

MIT License  
Copyright © 2025 Thomas Kuhlmann

---

## ⚡ Exit Codes

| Code | Meaning |
|------|----------|
| 0 | Execution successful |
| 1 | I/O or filesystem error |
| 2 | Invalid arguments |
| 3 | Pattern matched no files |
| 9 | Unexpected error |

---

## 💡 Tip

Use `--list-only` to integrate with external scripts or pipelines:

```bash
python3 retentions.py /data/logs '*.log' -d 3 -w 2 --list-only | while read f; do
    echo "Would delete $f"
done
```

---

Simple. Predictable. Cross-platform.  
Just **retentions**.