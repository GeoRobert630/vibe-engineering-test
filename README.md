# Vibe Engineering Test

External acceptance test for the three-gate **Engineering CI** (Security CI + Quality CI accessibility + Quality CI
performance orchestration) from [GeoRobert630/vibe-code-engineering](https://github.com/GeoRobert630/vibe-code-engineering).

- `.github/workflows/engineering-ci.yml` is an unchanged copy of
  `tools/engineering-ci/examples/github-actions-engineering-ci.yml` at Engineering CI commit `62461a6`
  (`62461a66e617fc7b5d7adda174d2d64ec217933d`). Its tooling pins are the toolkit's own: Security `bd71c46`
  (security-baseline-v1), Accessibility `fa816aa` (quality-ci-v1.1), Performance `c6b82c0` (quality-ci-v1.2).
- `.github/workflows/engineering-ci-cases.yml` calls it once per case (real pinned tools, no mocked results) and runs
  `.github/acceptance/assert_cases.py`, which checks the outputs and the downloaded report artifacts. The assert job
  also diffs the copy against the toolkit at the pinned commit. Run it manually with **Run workflow**
  (`workflow_dispatch`) or by pushing to `master`.

| Case | Contents | Pages | Security | Accessibility | Performance | Final |
|---|---|---|---|---|---|---|
| `cases/clean` | clean app + accessible page | `/` | PASS | PASS | PASS | PASS |
| `cases/vulnerable` | + intentionally vulnerable SQL-injection fixture | `/` | FAIL | PASS | PASS | FAIL |
| `cases/inaccessible` | clean app + intentionally inaccessible page | `/` | PASS | FAIL | PASS | FAIL |
| `cases/slow` | clean app + intentionally slow page | `/slow.html` | PASS | PASS | FAIL | FAIL |
| `cases/all-fail` | vulnerable + inaccessible + slow | `/ /slow.html` | FAIL | FAIL | FAIL | FAIL |

All cases run with `enforce: false`, so a FAIL result does not fail its own call; `clean-enforced` runs `cases/clean`
with the default `enforce: true` and must still succeed. The assertion also checks, per case:

- each gate's job ran to success and uploaded its own report, SARIF and gate output (gates are independent);
- separate SARIF outputs: `security.sarif` (`vibe-code-engineering/phase2/`), `accessibility.sarif`
  (`vibe-code-engineering/quality/accessibility/`), `performance.sarif` (`vibe-code-engineering/quality/performance/`),
  and three distinct code-scanning categories for the commit;
- namespaces: security findings `P2-*`/`RT-*`/`AI-*`, accessibility `Q-A11Y-*`, performance `Q-PERF-*`;
- no `security-severity` in the accessibility or performance SARIF;
- Authentication, Session and Authorization are NOT VERIFIED (no runtime target is configured).

Fixtures are copied unchanged from existing test fixtures (`vibe-security-test` commit `e96b3cc`,
`tools/quality-ci/fixtures` at `fa816aa`, and `tools/quality-ci/fixtures/performance/slow.*` + `img/shift.png` at
`c6b82c0`). They are **intentionally vulnerable / inaccessible / slow and exist only for CI testing**. They contain no
secrets.

The `engineering-ci` run triggered on push scans the whole repository with enforcement on. Because the repository
contains the vulnerable fixtures, that run is **expected to FAIL** (Security FAIL; Accessibility and Performance NOT
CONFIGURED). It shows that the combined gate is enforced.
