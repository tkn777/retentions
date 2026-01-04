# Release Policy

This project follows a deliberately minimal and conservative release model.

## Branches

- `main` is the only long-lived branch.
- Maintenance branches are created **only when needed**, never by default.

Maintenance branches start **no earlier than version 1.1**.

Naming:
```
maint-<major>.<minor>
```

Example:
```
maint-1.1
```

A maintenance branch is created only if:
- `main` has diverged with incompatible changes, and
- the released minor version still requires bugfixes.

Branches are always created from the latest stable tag of that minor version.

## Tags

- Every release is tagged.
- Tags are immutable and authoritative.
- Tags exist on `main` and on maintenance branches.

Examples:
```
v1.1.0
v1.1.1
v1.1.2
```

## Maintenance Branch Rules

- Only bugfixes are allowed.
- No refactors, cleanups, or new features.
- Commits must be small and suitable for cherry-picking.

## Backporting

- Bugfixes committed to `maint-*` must be cherry-picked to `main`.
- Fixes flow forward only.
- Maintenance branches are never merged back wholesale.

## Lifecycle

- Maintenance branches are temporary.
- Once no longer needed, they are deleted.
- Finished branches are not kept for archival purposes.

## Principle

- Tags preserve history.  
- Branches exist to solve active problems.
