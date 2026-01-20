# Release Policy

This project follows a deliberately minimal and conservative release model.

## Branches

* `main` is the only long-lived integration branch.
* Maintenance branches are created **only when needed**, never by default.
* Feature branches may exist temporarily alongside maintenance branches.

### Maintenance Branch Naming

```
maint/<major>.<minor>
```

Example:

```
maint/1.2
```

A maintenance branch is created only if:

* `main` has diverged with incompatible changes, and
* the released minor version still requires bugfixes.

Branches are always created from the latest stable tag of that minor version.

### Feature Branches

Feature branches are used for the development of new functionality or larger refactorings that are not suitable for a maintenance branch.

Naming:

```
feature/<short-description>
```

Examples:

```
feature/inline-retentions
feature/dynamic-retentions
```

Rules:

* Feature branches are created from `main`.
* Feature branches may diverge significantly from released versions.
* Feature branches are merged back into `main` only.
* Feature branches must never be merged into `maint-*` branches.

## Tags

* Every release is tagged.
* Tags are immutable and authoritative.
* Tags exist on `main` and on maintenance branches.

Examples:

```
v1.1.0
v1.1.1
v1.1.2
```

## Maintenance Branch Rules

* Only bugfixes are allowed.
* No refactors, cleanups, or new features.
* Commits must be small and suitable for cherry-picking.

## Backporting

* Bugfixes committed to `maint-*` must be cherry-picked to `main`.
* Fixes flow forward only.
* Maintenance branches are never merged back wholesale.

## Branch Namespace Rules

Branch categories are expressed via namespaces for clarity and consistency.

* `maint/*` denotes maintenance branches.
* `feature/*` denotes feature branches.

## Coexistence Rules

* Maintenance branches and feature branches may exist at the same time.
* Maintenance branches are treated as isolated and conservative.
* Feature branches ignore maintenance branches entirely.
* No direct merges occur between feature branches and maintenance branches.

## Lifecycle

* Maintenance branches are temporary.
* Feature branches are temporary.
* Once no longer needed, branches are deleted.
* Finished branches are not kept for archival purposes.

## Principle

* Tags preserve history.
* Branches exist to solve active problems.

## Release Checklist

* [ ] argparse options reviewed
* [ ] bash completion updated
* [ ] zsh completion updated
* [ ] man page updated
