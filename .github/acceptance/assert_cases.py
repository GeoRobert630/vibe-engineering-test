"""Acceptance assertions for the three-gate Engineering CI (engineering-ci-cases.yml).

Reads the reusable-workflow outputs of every case (NEEDS, the JSON of `needs`) and the report artifacts each case
uploaded (downloaded under ARTIFACTS_DIR/<artifact name>/). Checks only what the real pinned tools produced; it
creates no findings. Exit 0 when every case matches its expectation, 1 otherwise.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

GATES = ("security", "quality", "performance")
LABELS = {"security": "Security", "quality": "Accessibility", "performance": "Performance"}
# case -> (security, accessibility, performance, final, enforced)
EXPECTED = {
    "clean": ("PASS", "PASS", "PASS", "PASS", False),
    "vulnerable": ("FAIL", "PASS", "PASS", "FAIL", False),
    "inaccessible": ("PASS", "FAIL", "PASS", "FAIL", False),
    "slow": ("PASS", "PASS", "FAIL", "FAIL", False),
    "all-fail": ("FAIL", "FAIL", "FAIL", "FAIL", False),
    "clean-enforced": ("PASS", "PASS", "PASS", "PASS", True),
}
REPORTS = {
    "security": ("security-reports", "phase2/security-report.json", "security.sarif", "security-gate.txt"),
    "quality": ("quality-reports", "accessibility-report.json", "accessibility.sarif", "quality-gate.txt"),
    "performance": ("performance-reports", "performance-report.json", "performance.sarif", "performance-gate.txt"),
}
SECURITY_NAMESPACES = ("P2-", "RT-", "AI-")
NOT_VERIFIED = ("NOT VERIFIED",) * 3


def finding_ids(sarif: dict) -> list[str]:
    return [r.get("properties", {}).get("findingId", "") for run in sarif.get("runs", []) for r in run.get("results", [])]


def automation_ids(sarif: dict) -> set[str]:
    return {(run.get("automationDetails") or {}).get("id", "") for run in sarif.get("runs", [])}


def check_case(case: str, need: dict, root: Path) -> tuple[list[str], tuple[str, ...]]:
    sec, a11y, perf, final, enforced = EXPECTED[case]
    want = {"security": sec, "quality": a11y, "performance": perf}
    errors: list[str] = []
    out = need.get("outputs") or {}

    # Final enforcement: enforce:false keeps a FAIL from failing the call; enforce:true on PASS must not fail either.
    if need.get("result") != "success":
        errors.append(f"reusable workflow result {need.get('result')!r}, expected 'success'")
    if out.get("overall") != final:
        errors.append(f"overall {out.get('overall')!r}, expected {final}")
    for g in GATES:
        if out.get(f"{g}_status") != want[g] or out.get(f"{g}_gate") != want[g]:
            errors.append(f"{g} status/gate {out.get(f'{g}_status')!r}/{out.get(f'{g}_gate')!r}, expected {want[g]}")
    cov = tuple(out.get(k) for k in ("authentication", "session", "authorization"))
    if cov != NOT_VERIFIED:
        errors.append(f"authentication/session/authorization {cov}, expected NOT VERIFIED")

    suffix = f"-{case}"
    summary_path = root / f"engineering-reports{suffix}" / "engineering-summary.json"
    if not summary_path.is_file():
        errors.append(f"missing {summary_path}")
        summary = {}
    else:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("overall") != final:
            errors.append(f"summary overall {summary.get('overall')!r}")
        if summary.get("enforced") is not enforced:
            errors.append(f"summary enforced {summary.get('enforced')!r}, expected {enforced}")
        if tuple(summary.get("verification", {}).get(k) for k in ("authentication", "session", "authorization")) != NOT_VERIFIED:
            errors.append(f"summary verification {summary.get('verification')}")

    # Independence: every gate's job ran to success and produced its own report, SARIF and gate output,
    # whatever the other gates returned.
    sarifs: dict[str, dict] = {}
    for g in GATES:
        art, report, sarif, gate_txt = REPORTS[g]
        base = root / f"{art}{suffix}"
        if (summary.get(g) or {}).get("job_result") != "success":
            errors.append(f"{g} job_result {(summary.get(g) or {}).get('job_result')!r}, expected 'success'")
        for rel in (report, sarif, gate_txt):
            if not (base / rel).is_file():
                errors.append(f"missing {art}{suffix}/{rel}")
        if (base / sarif).is_file():
            sarifs[g] = json.loads((base / sarif).read_text(encoding="utf-8"))
        if (base / gate_txt).is_file():
            outcome = next((line.split(": ", 1)[1].strip() for line in (base / gate_txt).read_text(encoding="utf-8").splitlines()
                            if line.startswith("Outcome: ")), None)
            if g != "security" and outcome != want[g]:
                errors.append(f"{g} gate Outcome {outcome!r}, expected {want[g]}")

    # Separate SARIF outputs, namespaces and no security-severity outside the security SARIF.
    if len(sarifs) == 3:
        ids = {g: finding_ids(s) for g, s in sarifs.items()}
        auto = {g: automation_ids(s) for g, s in sarifs.items()}
        if any(auto[a] & auto[b] for a in GATES for b in GATES if a < b):
            errors.append(f"SARIF automationDetails overlap: {auto}")
        if not all(i.startswith("vibe-code-engineering/") and "quality" not in i for i in auto["security"]):
            errors.append(f"security SARIF automationDetails {auto['security']}")
        if auto["quality"] != {"vibe-code-engineering/quality/accessibility/"}:
            errors.append(f"accessibility SARIF automationDetails {auto['quality']}")
        if auto["performance"] != {"vibe-code-engineering/quality/performance/"}:
            errors.append(f"performance SARIF automationDetails {auto['performance']}")
        if not all(i.startswith(SECURITY_NAMESPACES) for i in ids["security"]):
            errors.append(f"security SARIF namespaces {ids['security']}")
        if not all(i.startswith("Q-A11Y-") for i in ids["quality"]):
            errors.append(f"accessibility SARIF namespaces {ids['quality']}")
        if not all(i.startswith("Q-PERF-") for i in ids["performance"]):
            errors.append(f"performance SARIF namespaces {ids['performance']}")
        for g, prefix in (("security", "P2-"), ("quality", "Q-A11Y-"), ("performance", "Q-PERF-")):
            errored = [r for run in sarifs[g].get("runs", []) for r in run.get("results", [])
                       if r.get("level") == "error" and r.get("properties", {}).get("findingId", "").startswith(prefix)]
            if want[g] == "FAIL" and not errored:
                errors.append(f"{g} FAIL without an error-level {prefix}* SARIF result")
        for g in ("quality", "performance"):
            if "security-severity" in json.dumps(sarifs[g]):
                errors.append(f"{g} SARIF contains security-severity")

    got = (out.get("security_status"), out.get("quality_status"), out.get("performance_status"), out.get("overall"))
    return errors, tuple(str(v) for v in got)


def check_code_scanning(repo: str, sha: str, ref: str, token: str) -> list[str]:
    """The three gates' SARIF uploads must exist for this commit under three distinct code-scanning categories."""
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/code-scanning/analyses?ref={ref}&per_page=100",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        analyses = [a for a in json.load(resp) if a.get("commit_sha") == sha]
    cats = sorted({a.get("category", "") for a in analyses})
    print("Code scanning categories for this commit:", ", ".join(cats) or "(none)")
    fam = {"security": [c for c in cats if "quality" not in c and ("security" in c or "phase2" in c)],
           "accessibility": [c for c in cats if "accessibility" in c],
           "performance": [c for c in cats if "performance" in c]}
    errors = [f"no {k} code-scanning category" for k, v in fam.items() if not v]
    if set(fam["security"]) & set(fam["accessibility"]) or set(fam["security"]) & set(fam["performance"]) \
            or set(fam["accessibility"]) & set(fam["performance"]):
        errors.append(f"code-scanning categories overlap: {fam}")
    for a in analyses:
        if "performance" in a.get("category", "") and "security" in json.dumps(a.get("tool", {})).lower():
            errors.append(f"performance analysis reported by a security tool: {a.get('tool')}")
    return errors


def main() -> int:
    needs = json.loads(os.environ["NEEDS"])
    root = Path(os.environ.get("ARTIFACTS_DIR", "artifacts"))
    bad = 0
    rows = ["Case | Security | Accessibility | Performance | Final", "---|---|---|---|---"]
    for case in EXPECTED:
        errors, got = check_case(case, needs.get(case, {}), root)
        rows.append(f"{case} | " + " | ".join(got))
        for e in errors:
            print(f"::error title={case}::{e}")
        bad += bool(errors)
        print(f"{case}: {'OK' if not errors else 'MISMATCH'}")
    if os.environ.get("CHECK_CODE_SCANNING") == "true":
        errors = check_code_scanning(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"], os.environ["GITHUB_REF"],
                                     os.environ["GH_TOKEN"])
        for e in errors:
            print(f"::error title=code scanning::{e}")
        bad += bool(errors)
    table = "\n".join(rows)
    print(table)
    print("Authentication / Session / Authorization: NOT VERIFIED in every case" if not bad else "")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(f"## Engineering CI acceptance: {'PASS' if not bad else 'FAIL'}\n\n{table}\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
