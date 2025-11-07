# retentions

A minimal cross-platform CLI tool for file retention management.  

It keeps only the most recent or representative files according to simple time-based rules and removes the rest.

---

## 🧩 Overview

`retentions` is a single-file Python script that applies retention logic to a directory of files. 

It groups files into time **buckets** (hours, days, weeks, months, years) and keeps only one representative file per bucket, typically the most recent one.  

Everything outside your defined retention scope is deleted (unless `--dry-run` or `--list-only` is used).

⚠️ **This software deletes files. Use at your own risk.**  
**The author assumes no responsibility for data loss or damage.**

---

## ⚙️ Features

- Pure **Python 3**, no external dependencies.  
- Runs on **Linux, macOS, and Windows**.  
- Keeps the **last N files** (`--last`) regardless of age.  
- Supports **hourly, daily, weekly, monthly, and yearly** retention buckets.  
- Supports **regex or glob** pattern matching.  
- Safe modes:  
  - `--dry-run` → simulate actions  
  - `--list-only` → output only files that would be deleted  
- Clean, deterministic output — ASCII only, no colors, no locales.

---

## 🧰 Installation

You can install **retentions** in several ways, depending on your system and preference.

### 🧩 Option 1 – Debian / Ubuntu (.deb)

Download the latest `.deb` package from the [Releases](https://github.com/tkn777/retentions/releases) page and install it manually:

```bash
sudo dpkg -i retentions_1.0.0.deb
```

This installs:
- `/usr/bin/retentions`
- documentation in `/usr/share/doc/retentions/`

### 🗜️ Option 2 – Universal (tar.gz)

For non-Debian systems or manual setups:

```bash
tar xzf retentions-0.1.0.tar.gz
sudo cp retentions.py /usr/local/bin/retentions
sudo chmod 755 /usr/local/bin/retentions
```

### ⚡ Option 3 – Direct (current version via wget)

For quick installs or testing:

```bash
sudo wget -O /usr/local/bin/retentions https://raw.githubusercontent.com/tkn777/retentions/main/retentions.py
sudo chmod 755 /usr/local/bin/retentions
```

To verify installation:

```bash
retentions --help
```

All installation methods require **Python 3.7+**.

No dependencies beyond Python 3.

---

## 🖥️ Usage

```bash
python3 retentions.py [path] [file_pattern] [options]
```

### Example

```bash
# Keep last 7 days, 4 weeks, 6 months
python3 retentions.py /data/backups '*.tar.gz' -d 7 -w 4 -m 6
```

### Dry run (no deletion)

```bash
python3 retentions.py /data/backups '*.tar.gz' -d 10 -w 3 -m 6 --dry-run
```

### List-only mode (for piping into other tools)

```bash
python3 retentions.py /data/backups '*.tar.gz' -d 5 -w 12 --list-only | xargs rm
```

### Verbose output

```bash
python3 retentions.py /data/backups '*.tar.gz' -d 3 -w 1 --verbose
```

---

## 🔧 Options

| Option | Description |
|--------|--------------|
| `path` | Base directory to scan |
| `file_pattern` | Regex or glob pattern for matching files |
| `-h, --hours <int>` | Keep all files modified within the last *N* hours |
| `-d, --days <int>` | Keep all files modified within the last *N* days |
| `-w, --weeks <int>` | Keep one file per week (last *N* weeks) |
| `-m, --months <int>` | Keep one file per month (last *N* months) |
| `-y, --years <int>` | Keep one file per year (last *N* years) |
| `-l, --last <int>` | Always keep the *N* most recent files |
| `--dry-run` | Show actions without deleting anything |
| `--list-only` | Output only file paths that would be deleted (incompatible with `--verbose`) |
| `--verbose` | Detailed output (KEEP/DELETE + reason) |

---

## 🧠 Logic Summary

1. **Collect all matching files** under the given path.  
2. **Sort** them by modification time (newest first).  
3. **Retain**:
   - Last `N` files (`--last`)
   - Files within the recent `hours` / `days`
   - Newest file per `week` / `month` / `year`
4. **Delete** everything else.  
5. If `--dry-run` is enabled, print the planned actions instead of executing them.

---

## 📦 Design Principles

- **KISS** – no configuration files, no hidden behavior.  
- **Deterministic** – same input, same output.  
- **Safe by intention** – dry-run and list-only modes available.  
- **Cross-platform** – works anywhere Python runs.  
- **Plain ASCII** – no colors, no locale dependencies.

---

## 🪶 License

MIT License  
Copyright © 2025

---

## ⚡ Exit Codes

| Code | Meaning |
|------|----------|
| 0 | Execution successful |
| 1 | Invalid arguments |
| 2 | I/O or filesystem error |
| 3 | Pattern matched no files |

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
