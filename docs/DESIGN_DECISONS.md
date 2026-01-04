## Common Design Decisions

- **Zero runtime dependencies**: the CLI follows a strict one-file policy to keep distribution simple and robust.
- **No configuration files:** all behavior is controlled via explicit CLI arguments.
- **No silent magic:** every action must be understandable and reproducible; no hidden heuristics.
- **No implicit recursion:** directory traversal is intentionally shallow to avoid accidental mass deletions.
- **No implicit interactive mode:** the tool is designed for automation, not conversation.
- The implementation follows a **parsimonious code style**: every additional line or heuristic must justify its existence. This principle applies not only to code structure, but also to user-facing behavior, error handling, and feature selection.
- **Conservative defaults**: when behavior is ambiguous or potentially dangerous, the tool prefers safety over convenience.

---

## Principles

The design of the CLI follows a few core principles:

- **Explicit is better than implicit:** every retention rule is opt-in and fully controlled by the user.
- **Human-readable first:** errors and help output should read naturally without requiring a manual.
- **Predictability:** the same arguments always produce the same behavior.
- **Fail early, fail clearly:** invalid arguments or incompatible flags are detected immediately.
- **Minimal surface area:** only essential functionality is exposed; complexity stays internal.

---

## Non-Goals
retentions intentionally does **not aim** to:
- manage backups or create snapshots
- traverse directory trees recursively
- infer retention rules automatically
- provide interactive confirmation dialogs
- recover from partially failed deletion runs

---

## Execution Model

1. Argument parsing and validation
2. File discovery (single-directory scope)
3. Retention decision phase (pure logic, no side effects)
4. Optional filtering phase
5. Deletion phase (or simulation / listing)

- **No filesystem modifications** occur before all retention and filtering decisions have been fully computed and validated.

---

## Integrity and Safety Guarantees

retentions enforces internal consistency checks before executing destructive actions:
- Every file must end up in exactly one of the sets: **keep or prune**.
- Mismatches between computed decisions and deletion candidates **abort execution**.
- A **lock file** prevents concurrent retention runs on the same directory by default.

---

## Parser Design

- **ModernStrictArgumentParser** overrides `error()` to produce clearer, trace-free error messages that behave consistently in CLI environments.
- **Option suggestions** are based on distance + fallback heuristics (Levenshtein-inspired) to improve UX without sacrificing performance.
- **Prohibit duplicate flags** to avoid ambiguous behavior.
- **Argument groups** structure the CLI help output into logically human-readable sections.
- **No error recovery**: invalid or ambiguous CLI input is rejected immediately instead of being interpreted heuristically.
- **Validation before execution**: all arguments are fully validated and normalized before any filesystem operation is performed.

---

## Retention Logic

- **Retention rules are applied additively**. A file kept by any rule remains kept unless explicitly filtered later. Time-based retention rules are processed in a fixed order, from finer to coarser granularity.
- **Global filters** such as --max-files, --max-size, and --max-age are applied after retention decisions, not instead of them. Filters may override previous keep decisions.
- **Decision logging**: for each file, retentions records not only the final action, but also the reasoning behind it. At higher verbosity levels, the full decision chain is preserved.
- **Single-directory scope**: retention rules are applied only to direct children of the given base directory.

---

## Completion Strategy

To maintain a dependency-free CLI:

- Shell completions are generated **outside the tool**, using a helper script.
- The helper imports `create_parser()`, ensuring completions always match the real CLI interface.
- `shtab` is used because it supports **bash** and **zsh** cleanly without altering the tool itself.
- **fish** is intentionally not supported, as it would require custom completion logic with high maintenance cost.
