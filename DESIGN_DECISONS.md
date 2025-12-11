## Common Design Decisions

- **Zero runtime dependencies**: the CLI follows a strict one-file policy to keep distribution simple and robust.
- **Shell completions** are generated externally using `shtab`, which consumes the real parser (`create_parser()`) without introducing dependencies into the CLI itself.
- **No implicit recursion:** directory traversal is intentionally shallow to avoid accidental mass deletions.
- **No configuration files:** all behavior is controlled via explicit CLI arguments.
- **No silent magic:** every action must be understandable and reproducible; no hidden heuristics.
- **No implicit interactive mode:** the tool is designed for automation, not conversation.

---

## Principles

The design of the CLI follows a few core principles:

- **Explicit is better than implicit:** every retention rule is opt-in and fully controlled by the user.
- **Human-readable first:** errors and help output should read naturally without requiring a manual.
- **Predictability:** the same arguments always produce the same behavior.
- **Fail early, fail clearly:** invalid arguments or incompatible flags are detected immediately.
- **Minimal surface area:** only essential functionality is exposed; complexity stays internal.

---

## Parser Design (Summary)

- **ModernStrictArgumentParser** overrides `error()` to produce clearer, trace-free error messages that behave consistently in CLI environments.
- **Option suggestions** are based on distance + fallback heuristics (Levenshtein-inspired) to improve UX without sacrificing performance.
- **Argument groups** structure the CLI help output into logically human-readable sections:

---

## Completion Strategy

To maintain a dependency-free CLI:

- Shell completions are generated **outside the tool**, using a helper script.
- The helper imports `create_parser()`, ensuring completions always match the real CLI interface.
- `shtab` is used because it supports **bash** and **zsh** cleanly without altering the tool itself.
- **fish** is intentionally not supported, as it would require custom completion logic with high maintenance cost.
