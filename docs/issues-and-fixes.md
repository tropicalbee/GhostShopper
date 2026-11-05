# Issues and fixes

## 2026-11-05

**pytest could not create temp dirs**
- Broke: every test using `tmp_path` errored with `PermissionError: [WinError 5] Access is denied: ...\Temp\pytest-of-shiba`.
- Root cause: pytest's shared base temp dir is not accessible in this sandboxed Windows environment; a fresh `tempfile.mkdtemp()` dir is.
- Fix: root `conftest.py` overrides `tmp_path` with `tempfile.mkdtemp(prefix="ghostshopper-test-")`. No automatic deletion.

**Jinja macro not visible in child templates**
- Broke (caught before running): `price()` macro defined in `base.html` is not callable from templates that extend it.
- Root cause: Jinja child templates only override blocks; top-level macros in the parent are not exported.
- Fix: moved it to `store/templates/_macros.html`, imported with `{% from "_macros.html" import price with context %}`.

**Two over-strict test assertions**
- Broke: `"FH-MUG-01" not in html` failed because the SKU is in the buy URL; `'class="act' not in html` matched `class="actions"`.
- Root cause: test assertions, not store behavior.
- Fix: assert on `SKU:` / `In stock` text and `'class="act '` (with trailing space).
