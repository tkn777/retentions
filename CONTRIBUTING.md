# Contributing to retentions

Thank you for considering contributing to **retentions**!\
This document describes how to set up your environment, report issues,
and submit changes.

------------------------------------------------------------------------

## Consider starting a discussion

Consider starting a **Discussion** before opening a pull request.\
This helps confirm that the idea fits the project goals and prevents
unnecessary work.

------------------------------------------------------------------------

## Getting Started

1.  Fork this repository and clone your fork:

    ``` bash
    git clone https://github.com/your-username/retentions.git
    cd retentions
    ```

2.  Create a virtual environment:

    ``` bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  Install the project and its development dependencies:

    ``` bash
    python -m pip install ".[dev]"
    ```

4.  Run the CLI:

    ``` bash
    python3 -m retentions --help
    ```

------------------------------------------------------------------------

## Code Style and Linting

This project supports Python 3.9 and newer. CI checks Python 3.9 through the
currently supported development versions.

This project uses **pytest**, **Ruff**, and **mypy** for testing, formatting,
linting, and type checking.

Run all checks before committing:

``` bash
python -m pytest
ruff check .
ruff format --check .
mypy .
```

Format automatically when needed:

``` bash
ruff format .
```

Behavior changes and bug fixes should include regression tests where practical.
Add user-visible changes to the `[Unreleased]` section of `CHANGELOG.md`.

------------------------------------------------------------------------

## Commit Messages

Keep commits focused and clear.\
Use conventional prefixes where helpful, for example:

-   `fix:` -- bug fixes
-   `feat:` -- new features
-   `docs:` -- documentation updates
-   `refactor:` -- internal changes
-   `test:` -- adding or improving tests

Example:

    feat: add --list-only separator option

------------------------------------------------------------------------

## Pull Requests

1.  Create a feature branch:

    ``` bash
    git checkout -b feature/my-change
    ```

2.  Commit and push your changes.

3.  Open a pull request against the `master` branch.

4.  Describe **what** the change does and **why** it's needed.

Small, focused PRs are preferred over large ones.

See [`RELEASE_POLICY.md`](./RELEASE_POLICY.md) for branch naming and release
requirements.

------------------------------------------------------------------------

## Reporting Issues

If you find a bug or have a feature request, please open an issue or start a discussion.\
Include details about your environment (`python --version`, OS, etc.)
and steps to reproduce the problem.

Security-related issues should **not** be reported here --- see
[`SECURITY.md`](./SECURITY.md).

------------------------------------------------------------------------

## License

By contributing, you agree that your contributions will be licensed
under the same terms as this project --- the **MIT License**.
