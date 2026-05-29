# testhide-unittest-plugin

Emit **Testhide-format** (JUnit-extended) test reports straight from Python's built-in
[`unittest`](https://docs.python.org/3/library/unittest.html) — so the Testhide build agent
parses your results correctly and the dashboard/AI features get full data, with zero manual XML.

It produces the exact same contract as
[`testhide-pytest-plugin`](https://github.com/thuesdays/testhide-pytest-plugin): `fail_id`,
`test_resolution`, `docstr`/`attachment`/`info`/`jira` properties, `<system-out>`, suite
metadata, and `testhide_schema_version=1`. See the canonical spec:
[Testhide Report Format v1](https://testhide.com/plugins/report-format/).

## Install

```bash
pip install testhide-unittest-plugin
# optional Jira enrichment:
pip install "testhide-unittest-plugin[jira]"
```

## Usage

### CLI (recommended) — a thin wrapper over `unittest`

```bash
# discover & run, writing the report:
python -m testhide_unittest discover -s tests -p "test_*.py" --report-xml junittests.xml

# run specific modules/classes:
python -m testhide_unittest tests.test_login --report-xml junittests.xml
```

Anything `unittest` accepts is passed through; Testhide options are consumed by the wrapper:

| Option | Meaning |
|---|---|
| `--report-xml PATH` | output report (default `junittests.xml`) |
| `--suite-name NAME` | `<testsuite name="...">` (default `unittest`) |
| `--quarantine-file PATH` | skip listed test ids (also `TESTHIDE_QUARANTINE_FILE` / `.testhide_quarantine_file`) |
| `--meta KEY=VALUE` | add a suite `<property>` (repeatable; e.g. `--meta build=1042 --meta branch=main`) |
| `--no-capture` | do not capture stdout/stderr into `<system-out>` |
| `--jira-url / --jira-username / --jira-password` | optional Jira enrichment by `fail_id` |

Exit code is `0` when all tests pass, `1` otherwise — drop it straight into CI.

### Programmatic

```python
import unittest
import testhide_unittest

runner = testhide_unittest.TesthideTestRunner(
    report_path="junittests.xml",
    metadata={"build": "1042", "branch": "main"},
)
unittest.main(testRunner=runner)
```

### Enrich a test's report entry

```python
import unittest
import testhide_unittest as th

class LoginTests(unittest.TestCase):
    def test_login(self):
        "User can log in with valid credentials."   # docstring -> docstr (automatic)
        th.attach("/tmp/screenshot.png")            # repeatable; images/logs/json
        th.set_info('{"env": "staging"}')           # free-form context
        th.set_jira("PROJ-123")                     # link a ticket
        ...
```

## What it captures

- Outcomes: pass / fail / error / skip / `@expectedFailure` (→ `Known Issue`) / unexpected pass.
- `fail_id` = `md5("module.class.function.ExceptionType(message)")` — stable failure key for
  dedup + Jira linkage (identical to the pytest plugin).
- `file` / `line` (for code-impact matching), test duration, docstring, attachments, info, jira,
  and captured stdout/stderr in `<system-out>`.
- Suite metadata: hostname, ip, `testhide_schema_version`, plus your `--meta` properties.

## Parallel / sharded runs

The writer is parallel-safe: each test is written to a temp chunk under `.{report}_temp/`, then
atomically merged into the final report (file-locked). Counts are recomputed on merge.

## Conformance

`conformance/` vendors the canonical validator + golden fixture. CI runs the plugin against a
sample suite and validates the output, guaranteeing the agent will parse it:

```bash
python conformance/validate_report.py junittests.xml
```

## Publishing (maintainers)

**Local publish (Windows):**
```bat
copy .env.local.example .env.local   :: then edit .env.local and add PYPI_API_TOKEN
publish.bat
```
`publish.bat` loads `.env.local` (gitignored), runs the conformance tests, builds the
sdist + wheel, and uploads to PyPI with `twine`.

`.env.local`:
```
PYPI_API_TOKEN=pypi-...      # https://pypi.org/manage/account/token/
```

**CI publish (GitHub Actions):** pushing to `main` auto-publishes (conformance gate → patch
version bump → PyPI → GitHub Release; loop-guarded so the bump commit doesn't re-trigger).
Required repository secret:
- `PYPI_API_TOKEN` — PyPI API token (Settings → Secrets and variables → Actions).

## License

MIT.
