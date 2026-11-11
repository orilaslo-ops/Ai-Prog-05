# Chess workshop

Python 3.10+ chess game; see README.md for the rules, files and lab tasks.

## Setup

The `.venv` has no pip; install the dev tools with uv:

```sh
source .venv/bin/activate
uv pip install -r requirements-dev.txt
```

`tests/test_browser.py` drives the page in Chromium with Playwright. If Chromium is
missing, run `playwright install chromium` once; without it those tests are skipped.

## Checks

Run all of these before committing; each must pass with no errors:

```sh
ruff check .
ruff format --check .
mypy --strict .
python -m pytest --cov --cov-report=term-missing
```

Keep new code fully type-annotated (`mypy --strict`) and formatted with `ruff format`.
Add tests in `tests/` for every behavior you add, following the existing test style.
