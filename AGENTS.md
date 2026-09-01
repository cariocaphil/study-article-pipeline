# Agent quality gates

Run these before opening a pull request:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -m "not slow"
```

Install Git pre-commit hooks once per clone (auto-formats and fixes Ruff issues on commit):

```bash
uv run pre-commit install
```

CI (`.github/workflows/ci.yml`) runs the same Ruff, Pyright, and fast pytest checks on pushes and pull requests to `main`.

Pipeline architecture, agent contracts, and eval workflows are documented in `CLAUDE.md`.
