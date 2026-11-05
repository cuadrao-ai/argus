# Issue #852 local SciPy runtime verification

Date: 2026-10-05. Host: macOS 27.0.1, Darwin 27.0.0, arm64.

The shared Python 3.10.20 environment was read only. `import scipy` succeeds, but `import scipy.linalg` fails while loading SciPy 1.15.3's `_spropack.cpython-310-darwin.so`:

```text
ImportError: ... section '__DATA/__thread_bss' has a zero-fill section type, but offset field is not zero
```

The original and freshly installed 1.15.3 `_spropack` files both have SHA-256 `dad5761989d85578a9daa55821c31e92ecea17fab414a0bd2075fd27f11c405f`. `otool -l` shows the `__thread_bss` section has offset `114992`. Reinstalling the same wheel therefore reproduces the bad binary; it does not repair the runtime. [SciPy issue #25635](https://github.com/scipy/scipy/issues/25635) reports the same loader symptom. [SciPy 1.17.0 notes](https://docs.scipy.org/doc/scipy/release/1.17.0-notes.html) describe its PROPACK rewrite from Fortran to C.

The unchanged `poetry.lock` (SHA-256 `3adb4550d2a882d148482e15e29f6f26e4107ce84d821fa3675e4e0f624f33ab`) selects SciPy 1.15.3 and NumPy 2.0.2 for Python 3.10, and SciPy 1.17.1 and NumPy 2.3.5 for Python 3.11 and newer. The already installed uv-managed CPython 3.11.15 was used to create `/private/tmp/cuadrao-scipy-env-20261005`. `poetry install --no-root --no-interaction` installed 206 locked packages into this isolated virtual environment. No repository dependency files or shared virtual environment files changed.

Creation and import preflight:

```sh
UV_CACHE_DIR=/private/tmp/cuadrao-scipy-uv-cache-20261005 uv venv --python /Users/garces/.local/share/uv/python/cpython-3.11-macos-aarch64-none/bin/python3.11 /private/tmp/cuadrao-scipy-env-20261005
env VIRTUAL_ENV=/private/tmp/cuadrao-scipy-env-20261005 PATH=/private/tmp/cuadrao-scipy-env-20261005/bin:/opt/homebrew/bin:/usr/bin:/bin POETRY_VIRTUALENVS_CREATE=false POETRY_CACHE_DIR=/private/tmp/cuadrao-scipy-poetry-cache-20261005 poetry install --no-root --no-interaction
/private/tmp/cuadrao-scipy-env-20261005/bin/python -c 'import sys,numpy,scipy,scipy.linalg,scipy.sparse.linalg; print(sys.version.split()[0],numpy.__version__,scipy.__version__,scipy.__file__); print("scipy.linalg OK; scipy.sparse.linalg OK")'
```

Output:

```text
3.11.15 2.3.5 1.17.1 /private/tmp/cuadrao-scipy-env-20261005/lib/python3.11/site-packages/scipy/__init__.py
scipy.linalg OK; scipy.sparse.linalg OK
```

The first test invocation stopped at collection because `argus_display_contract` lives under `web/` and `poetry install --no-root` did not install the Argus root package. Adding `PYTHONPATH=web:src:.` supplied the repository's own package source. This changes the local import path, not test or application behavior.

From each checkout, this exact command exercised four profile cases plus both parameterized home-country chat cases. It contains no live provider configuration or paid calls:

```sh
env PYTHONPATH=web:src:. PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=/private/tmp/cuadrao-scipy-numba-cache-20261005 /private/tmp/cuadrao-scipy-env-20261005/bin/python -m pytest tests/test_alpha_api_supabase.py::test_patch_me_supabase_ignores_retired_profile_fields tests/test_alpha_api_supabase.py::test_patch_me_persists_a_curated_avatar_theme tests/test_alpha_api_supabase.py::test_patch_me_rejects_an_unknown_avatar_theme tests/test_alpha_api_supabase.py::test_patch_me_rejects_a_null_avatar_theme tests/test_home_country.py::test_a_chat_turn_reads_the_country_from_the_profile -q -o addopts='' -p no:cacheprovider
```

| Source checkout | Exact HEAD | Result |
| --- | --- | --- |
| `/private/tmp/cuadrao-trust-20261005` | `875de09ac2115acec42e09060b92878aa5f18eff` | `6 passed in 11.18s` |
| `/private/tmp/cuadrao-primary-currency-20261005` | `9d213539fd465eb56e8e1a23d3ecd5933854e079` | `6 passed in 4.69s` |

Both source checkouts have clean tracked files after the runs. Their prior untracked evidence and `todo.md` files remain. The temporary virtual environment is local verification only; it does not prove that the Python 3.10 install works on macOS 27.
