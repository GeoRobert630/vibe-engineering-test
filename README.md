# Vibe Engineering Test

External integration test for **Engineering CI** (Security CI + Quality CI orchestration) from
[GeoRobert630/vibe-code-engineering](https://github.com/GeoRobert630/vibe-code-engineering).

- `.github/workflows/engineering-ci.yml` is an unchanged copy of
  `tools/engineering-ci/examples/github-actions-engineering-ci.yml`. Security tooling pinned to `bd71c46`
  (security-baseline-v1), Quality tooling pinned to `fa816aa` (quality-ci-v1.1).
- `.github/workflows/engineering-ci-cases.yml` calls it once per case and asserts the combined results.

| Case | Contents | Security gate | Quality gate | Overall |
|---|---|---|---|---|
| `cases/a-clean` | clean app + accessible page | PASS | PASS | PASS |
| `cases/b-security` | + intentionally vulnerable SQL-injection fixture | FAIL | PASS | FAIL |
| `cases/c-quality` | clean app + intentionally inaccessible page | PASS | FAIL | FAIL |
| `cases/d-both` | both | FAIL | FAIL | FAIL |

Fixtures are copied from existing test fixtures (`vibe-security-test` commit `e96b3cc`, and `tools/quality-ci/fixtures`
at `fa816aa`). They are **intentionally vulnerable / inaccessible and exist only for CI testing**. They contain no
secrets. No runtime target is configured, so Authentication, Session and Authorization are reported NOT VERIFIED.

The `engineering-ci` run triggered on push scans the whole repository with enforcement on. Because the repository
contains the vulnerable fixtures, that run is **expected to FAIL** (Security FAIL; Quality NOT CONFIGURED). It shows
that the combined gate is enforced.
