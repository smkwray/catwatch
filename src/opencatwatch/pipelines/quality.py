from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from ..config import Settings
from ..utils import normalize_name, read_json, read_jsonl, write_json

RELEASE_THRESHOLDS = {
    "sponsor_coverage_pct": 70.0,
    "region_coverage_pct": 95.0,
    "outstanding_missing_maturity": 40,
    "broad_peril_rows": 25,
    "dashboard_max_age_days": 14,
}

_PLACEHOLDER_USER_AGENT_MARKERS = {
    "you@example.com",
    "research project",
    "set opencatwatch_user_agent",
}

_MANUAL_TABLE_SPECS = {
    "sponsor_aliases": {
        "path": "sponsor_aliases.csv",
        "required_columns": ["alias", "sponsor_name", "source_url", "notes"],
        "row_label_field": "alias",
    },
    "tranche_overrides": {
        "path": "tranche_overrides.csv",
        "required_columns": ["tranche_name", "field_name", "override_value", "source_url", "notes"],
        "row_label_field": "tranche_name",
    },
}


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def _canonical_sponsor(row: dict) -> str | None:
    return row.get("sponsor_name") or row.get("sec_sponsor_name")


def _load_dashboard(settings: Settings) -> dict:
    dashboard_path = settings.data_dir.parent / "apps" / "site" / "data" / "dashboard.json"
    if not dashboard_path.exists():
        return {}
    payload = read_json(dashboard_path)
    return payload if isinstance(payload, dict) else {}


def _dashboard_age_days(dashboard: dict) -> int | None:
    as_of = _to_date(dashboard.get("as_of"))
    if not as_of:
        return None
    return max(0, (date.today() - as_of).days)


def _has_real_user_agent(user_agent: str) -> bool:
    normalized = (user_agent or "").strip().lower()
    if not normalized:
        return False
    return all(marker not in normalized for marker in _PLACEHOLDER_USER_AGENT_MARKERS)


def _family_name(row: dict) -> str:
    issuer_name = (row.get("issuer_name") or "").strip()
    if issuer_name:
        return issuer_name
    tranche_name = (row.get("tranche_name") or "").strip()
    for separator in (" Series ", " series ", " due ", " Due ", " Class ", " class "):
        if separator in tranche_name:
            return tranche_name.split(separator, 1)[0].strip()
    return tranche_name or "unknown"


def _load_manual_table_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def _validate_json_list_field(value: str | None) -> bool:
    if not value:
        return True
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, list)


def _validate_manual_tables(settings: Settings) -> dict:
    issues: list[dict[str, object]] = []
    summary: dict[str, dict[str, int]] = {}

    for table_name, spec in _MANUAL_TABLE_SPECS.items():
        path = settings.manual_dir / spec["path"]
        fieldnames, rows = _load_manual_table_rows(path)
        missing_columns = [column for column in spec["required_columns"] if column not in fieldnames]
        summary[table_name] = {"rows": len(rows), "issues": 0}
        if missing_columns:
            issues.append(
                {
                    "table": table_name,
                    "path": str(path),
                    "row_number": 1,
                    "label": table_name,
                    "issue": f"missing_required_columns:{','.join(missing_columns)}",
                }
            )
            summary[table_name]["issues"] += 1
            continue

        for index, row in enumerate(rows, start=2):
            label = (row.get(spec["row_label_field"]) or "").strip() or table_name
            if not (row.get("source_url") or "").strip():
                issues.append(
                    {
                        "table": table_name,
                        "path": str(path),
                        "row_number": index,
                        "label": label,
                        "issue": "missing_source_url",
                    }
                )
                summary[table_name]["issues"] += 1
            if not (row.get("notes") or "").strip():
                issues.append(
                    {
                        "table": table_name,
                        "path": str(path),
                        "row_number": index,
                        "label": label,
                        "issue": "missing_notes",
                    }
                )
                summary[table_name]["issues"] += 1
            for json_field in ("region_codes", "peril_codes"):
                if json_field in row and not _validate_json_list_field(row.get(json_field)):
                    issues.append(
                        {
                            "table": table_name,
                            "path": str(path),
                            "row_number": index,
                            "label": label,
                            "issue": f"invalid_json_list:{json_field}",
                        }
                    )
                    summary[table_name]["issues"] += 1

    return {"summary": summary, "issues": issues}


def _dashboard_has_evidence_fields(dashboard: dict) -> bool:
    maturity_rows = dashboard.get("maturity_wall") or []
    watchlist_rows = dashboard.get("watchlist") or []

    maturity_ok = all(
        isinstance(row, dict)
        and {"source_url", "sponsor_source_url", "sponsor_source_type", "review_status"} <= set(row)
        for row in maturity_rows[:5]
    )
    watchlist_ok = all(
        isinstance(row, dict)
        and {"source_url", "reason_text", "matched_tranche_rows"} <= set(row)
        for row in watchlist_rows[:5]
    )
    return maturity_ok and watchlist_ok


def _public_limitations(material: list[dict]) -> list[str]:
    families: dict[str, Counter[str]] = defaultdict(Counter)
    for row in material:
        family = _family_name(row)
        if not _canonical_sponsor(row):
            families[family]["missing sponsor evidence"] += 1
        if not row.get("region_codes"):
            families[family]["missing region evidence"] += 1
        if "other_property_cat" in (row.get("peril_codes") or []):
            families[family]["broad peril classification"] += 1
        if row.get("status") == "outstanding" and not row.get("maturity_date"):
            families[family]["missing maturity"] += 1

    ranked = sorted(
        (
            (family, counts, sum(counts.values()))
            for family, counts in families.items()
            if counts
        ),
        key=lambda item: (-item[2], item[0]),
    )

    limitations: list[str] = []
    for family, counts, _ in ranked[:8]:
        issue_text = ", ".join(f"{count} {issue}" for issue, count in counts.most_common(3))
        limitations.append(f"{family}: {issue_text}.")
    return limitations


def _build_release_checks(
    settings: Settings,
    coverage: dict,
    issues: dict,
    dashboard: dict,
    manual_tables: dict,
    public_limitations: list[str],
) -> list[dict]:
    dashboard_age_days = _dashboard_age_days(dashboard)
    manual_issue_count = len(manual_tables.get("issues", []))
    checks = [
        {
            "name": "sponsor_coverage",
            "passed": float(coverage.get("sponsor_coverage_pct", 0.0)) >= RELEASE_THRESHOLDS["sponsor_coverage_pct"],
            "actual": coverage.get("sponsor_coverage_pct", 0.0),
            "target": f">={RELEASE_THRESHOLDS['sponsor_coverage_pct']}",
            "detail": "Sponsor coverage on material tranches.",
        },
        {
            "name": "region_coverage",
            "passed": float(coverage.get("region_coverage_pct", 0.0)) >= RELEASE_THRESHOLDS["region_coverage_pct"],
            "actual": coverage.get("region_coverage_pct", 0.0),
            "target": f">={RELEASE_THRESHOLDS['region_coverage_pct']}",
            "detail": "Region coverage on material tranches.",
        },
        {
            "name": "outstanding_missing_maturity",
            "passed": int(issues.get("outstanding_missing_maturity", 0))
            <= RELEASE_THRESHOLDS["outstanding_missing_maturity"],
            "actual": issues.get("outstanding_missing_maturity", 0),
            "target": f"<={RELEASE_THRESHOLDS['outstanding_missing_maturity']}",
            "detail": "Outstanding material rows without maturity.",
        },
        {
            "name": "broad_peril_rows",
            "passed": int(issues.get("broad_peril_rows", 0)) <= RELEASE_THRESHOLDS["broad_peril_rows"],
            "actual": issues.get("broad_peril_rows", 0),
            "target": f"<={RELEASE_THRESHOLDS['broad_peril_rows']}",
            "detail": "Registry rows still using other_property_cat.",
        },
        {
            "name": "dashboard_not_demo",
            "passed": bool(dashboard) and not bool(dashboard.get("demo_mode")),
            "actual": bool(dashboard) and not bool(dashboard.get("demo_mode")),
            "target": True,
            "detail": "Committed dashboard snapshot is present and non-demo.",
        },
        {
            "name": "dashboard_current",
            "passed": dashboard_age_days is not None and dashboard_age_days <= RELEASE_THRESHOLDS["dashboard_max_age_days"],
            "actual": dashboard_age_days,
            "target": f"<={RELEASE_THRESHOLDS['dashboard_max_age_days']} days",
            "detail": "Dashboard as_of date is recent enough for public release.",
        },
        {
            "name": "dashboard_evidence_fields",
            "passed": _dashboard_has_evidence_fields(dashboard),
            "actual": _dashboard_has_evidence_fields(dashboard),
            "target": True,
            "detail": "Dashboard payload exposes evidence-facing fields for site rendering.",
        },
        {
            "name": "manual_evidence_metadata",
            "passed": manual_issue_count == 0,
            "actual": manual_issue_count,
            "target": 0,
            "detail": "Manual evidence tables include source_url and notes on every row.",
        },
        {
            "name": "non_placeholder_user_agent",
            "passed": _has_real_user_agent(settings.user_agent),
            "actual": _has_real_user_agent(settings.user_agent),
            "target": "real contact string",
            "detail": "Live fetches require a real operator contact string.",
        },
        {
            "name": "public_limitations_present",
            "passed": bool(public_limitations),
            "actual": len(public_limitations),
            "target": ">=1",
            "detail": "Remaining unresolved families are called out in public limitations text.",
        },
    ]
    return checks


def collect_audit_payload(settings: Settings) -> dict:
    tranches = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")
    matches = read_jsonl(settings.processed_dir / "watchlist" / "matches.jsonl")
    events = read_jsonl(settings.processed_dir / "watchlist" / "events.jsonl")
    dashboard = _load_dashboard(settings)
    manual_tables = _validate_manual_tables(settings)

    as_of = date.today()
    horizon = as_of + timedelta(days=365)
    material = [row for row in tranches if not row.get("is_programme_shell")]
    sponsor_rows = [row for row in material if _canonical_sponsor(row)]
    region_rows = [row for row in material if row.get("region_codes")]
    broad_matches = [row for row in matches if "broad_peril_match" in (row.get("reasons") or [])]
    unknown_region_matches = [row for row in matches if "region_unknown" in (row.get("reasons") or [])]
    actual_next_12m = sum(
        1
        for row in material
        if row.get("status") == "outstanding"
        and (maturity_date := _to_date(row.get("maturity_date")))
        and as_of <= maturity_date <= horizon
    )

    review_candidates = []
    for row in material:
        issues_for_row: list[str] = []
        if not _canonical_sponsor(row):
            issues_for_row.append("missing_sponsor")
        if not row.get("region_codes"):
            issues_for_row.append("missing_region")
        if "other_property_cat" in (row.get("peril_codes") or []):
            issues_for_row.append("broad_peril")
        if row.get("status") == "outstanding" and not row.get("maturity_date"):
            issues_for_row.append("missing_maturity")
        if not issues_for_row:
            continue
        priority = (
            4 * int("missing_sponsor" in issues_for_row)
            + 3 * int("missing_region" in issues_for_row)
            + 2 * int("broad_peril" in issues_for_row)
            + 1 * int("missing_maturity" in issues_for_row)
        )
        review_candidates.append(
            {
                "tranche_name": row.get("tranche_name"),
                "issuer_name": row.get("issuer_name"),
                "family_name": _family_name(row),
                "issues": issues_for_row,
                "priority": priority,
                "source_url": row.get("source_url"),
            }
        )
    review_candidates.sort(key=lambda row: (-row.get("priority", 0), row.get("tranche_name") or ""))

    coverage = {
        "sponsor_coverage_pct": round((len(sponsor_rows) / len(material) * 100.0), 2) if material else 0.0,
        "region_coverage_pct": round((len(region_rows) / len(material) * 100.0), 2) if material else 0.0,
        "identified_sponsors": len({_canonical_sponsor(row) for row in material if _canonical_sponsor(row)}),
        "inferred_region_rows": sum(
            1
            for row in material
            if row.get("region_inference_method") not in {None, "missing", "explicit_text"}
        ),
    }
    issue_counts = {
        "broad_peril_matches": len(broad_matches),
        "unknown_region_matches": len(unknown_region_matches),
        "outstanding_missing_maturity": sum(
            1 for row in material if row.get("status") == "outstanding" and not row.get("maturity_date")
        ),
        "broad_peril_rows": sum(1 for row in material if "other_property_cat" in (row.get("peril_codes") or [])),
    }
    public_limitations = _public_limitations(material)
    release_checks = _build_release_checks(
        settings=settings,
        coverage=coverage,
        issues=issue_counts,
        dashboard=dashboard,
        manual_tables=manual_tables,
        public_limitations=public_limitations,
    )

    return {
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "counts": {
            "tranches": len(tranches),
            "material_tranches": len(material),
            "programme_shells": sum(1 for row in tranches if row.get("is_programme_shell")),
            "watchlist_matches": len(matches),
            "watchlist_events": len(events),
        },
        "coverage": coverage,
        "issues": issue_counts,
        "dashboard_consistency": {
            "actual_next_12m_maturities": actual_next_12m,
            "dashboard_next_12m_maturities": ((dashboard.get("kpis") or {}).get("next_12m_maturities"))
            if dashboard
            else None,
            "next_12m_gap": (((dashboard.get("kpis") or {}).get("next_12m_maturities", 0)) - actual_next_12m)
            if dashboard
            else None,
            "dashboard_demo_mode": bool(dashboard.get("demo_mode")) if dashboard else None,
            "dashboard_age_days": _dashboard_age_days(dashboard),
        },
        "manual_evidence": manual_tables,
        "public_limitations": public_limitations,
        "release_gate": {
            "passed": all(check["passed"] for check in release_checks),
            "checks": release_checks,
            "failed_checks": [check["name"] for check in release_checks if not check["passed"]],
        },
        "top_review_candidates": review_candidates[:25],
    }


def _render_markdown(payload: dict) -> str:
    counts = payload.get("counts", {})
    coverage = payload.get("coverage", {})
    issues = payload.get("issues", {})
    dashboard = payload.get("dashboard_consistency", {})
    manual_evidence = payload.get("manual_evidence", {})
    lines = [
        "# OpenCatWatch data audit",
        "",
        f"Generated: {payload.get('generated_at', '')}",
        "",
        "## Release gate",
        "",
        f"- Passed: {payload.get('release_gate', {}).get('passed', False)}",
    ]
    for check in payload.get("release_gate", {}).get("checks", []):
        lines.append(
            f"- {check.get('name')}: {'pass' if check.get('passed') else 'fail'} "
            f"(actual={check.get('actual')}, target={check.get('target')})"
        )
    lines.extend(
        [
            "",
            "## Counts",
            "",
            f"- Tranches: {counts.get('tranches', 0)}",
            f"- Material tranches: {counts.get('material_tranches', 0)}",
            f"- Programme shells: {counts.get('programme_shells', 0)}",
            f"- Watchlist matches: {counts.get('watchlist_matches', 0)}",
            f"- Watchlist events: {counts.get('watchlist_events', 0)}",
            "",
            "## Coverage",
            "",
            f"- Sponsor coverage: {coverage.get('sponsor_coverage_pct', 0.0):.1f}%",
            f"- Region coverage: {coverage.get('region_coverage_pct', 0.0):.1f}%",
            f"- Identified sponsors: {coverage.get('identified_sponsors', 0)}",
            f"- Inferred regions: {coverage.get('inferred_region_rows', 0)}",
            "",
            "## Issues",
            "",
            f"- Broad peril matches: {issues.get('broad_peril_matches', 0)}",
            f"- Unknown-region matches: {issues.get('unknown_region_matches', 0)}",
            f"- Outstanding rows without maturity: {issues.get('outstanding_missing_maturity', 0)}",
            f"- Broad peril rows in registry: {issues.get('broad_peril_rows', 0)}",
            "",
            "## Dashboard consistency",
            "",
            f"- Actual next 12m maturities: {dashboard.get('actual_next_12m_maturities', 0)}",
            f"- Dashboard next 12m maturities: {dashboard.get('dashboard_next_12m_maturities', 0)}",
            f"- Gap: {dashboard.get('next_12m_gap', 0)}",
            f"- Demo mode: {dashboard.get('dashboard_demo_mode')}",
            f"- Dashboard age (days): {dashboard.get('dashboard_age_days')}",
            "",
            "## Manual evidence",
            "",
        ]
    )
    for table_name, summary in (manual_evidence.get("summary") or {}).items():
        lines.append(f"- {table_name}: {summary.get('rows', 0)} rows, {summary.get('issues', 0)} issues")
    for issue in (manual_evidence.get("issues") or [])[:20]:
        lines.append(
            f"- {issue.get('table')} row {issue.get('row_number')}: {issue.get('label')} [{issue.get('issue')}]"
        )
    lines.extend(["", "## Public limitations", ""])
    for limitation in payload.get("public_limitations", []):
        lines.append(f"- {limitation}")
    lines.extend(["", "## Top review candidates", ""])
    for row in payload.get("top_review_candidates", []):
        lines.append(f"- {row.get('tranche_name', 'unknown')}: {', '.join(row.get('issues', []))}")
    lines.append("")
    return "\n".join(lines)


def audit_processed_data(settings: Settings) -> str:
    payload = collect_audit_payload(settings)
    reports_dir = settings.data_dir.parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    write_json(reports_dir / "data_audit.json", payload)
    (reports_dir / "data_audit.md").write_text(_render_markdown(payload), encoding="utf-8")
    return str(reports_dir / "data_audit.md")


def run_release_check(settings: Settings) -> str:
    project_root = Path(__file__).resolve().parents[3]
    env = dict(os.environ)
    src_path = str(project_root / "src")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}:{existing_pythonpath}"

    subprocess.run([sys.executable, "-m", "ruff", "check", "src/opencatwatch", "tests"], check=True, cwd=project_root, env=env)
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-o", "cache_dir=/tmp/catwatch-pytest-cache"],
        check=True,
        cwd=project_root,
        env=env,
    )

    from .registry import build_registry
    from .site_data import build_site_data
    from .watchlist import build_watchlist

    build_registry(settings=settings)
    build_watchlist(settings=settings)
    build_site_data(settings=settings)
    audit_path = audit_processed_data(settings=settings)
    build_manual_review_queue(settings=settings)

    payload = read_json(Path(audit_path).with_suffix(".json"))
    failed_checks = (payload.get("release_gate") or {}).get("failed_checks") or []
    if failed_checks:
        raise RuntimeError(f"release gate failed: {', '.join(failed_checks)}")
    return audit_path


def build_manual_review_queue(settings: Settings, limit: int = 250) -> str:
    tranches = read_jsonl(settings.processed_dir / "registry" / "tranches.jsonl")
    queue_rows: list[dict[str, str | int]] = []
    for row in tranches:
        is_programme_shell = bool(row.get("is_programme_shell"))
        issues: list[str] = []
        actions: list[str] = []
        if is_programme_shell:
            issues.append("programme_shell")
            actions.append("verify if this should be excluded from watchlist + KPIs")
        if not _canonical_sponsor(row):
            issues.append("missing_sponsor")
            actions.append("look for sponsor in SEC/BMA/manual overrides")
        if not row.get("region_codes"):
            issues.append("missing_region")
            actions.append("set region_codes via manual override or issuer geography")
        if "other_property_cat" in (row.get("peril_codes") or []):
            issues.append("broad_peril")
            actions.append("replace broad peril with explicit peril if evidence exists")
        if row.get("status") == "outstanding" and not row.get("maturity_date"):
            issues.append("missing_maturity")
            actions.append("confirm maturity / risk end date")
        if not issues:
            continue
        priority = (
            4 * int("missing_sponsor" in issues)
            + 3 * int("missing_region" in issues)
            + 2 * int("broad_peril" in issues)
            + 1 * int("missing_maturity" in issues)
        )
        queue_rows.append(
            {
                "priority": priority,
                "is_programme_shell": is_programme_shell,
                "tranche_name": row.get("tranche_name") or "",
                "record_type": row.get("record_type") or "",
                "status": row.get("status") or "",
                "issues": "; ".join(issues),
                "recommended_actions": "; ".join(actions),
                "sponsor_name": _canonical_sponsor(row) or "",
                "issuer_name": row.get("issuer_name") or "",
                "peril_codes": ", ".join(row.get("peril_codes") or []),
                "region_codes": ", ".join(row.get("region_codes") or []),
                "maturity_date": row.get("maturity_date") or "",
                "source_url": row.get("source_url") or "",
            }
        )
    queue_rows.sort(
        key=lambda row: (
            int(bool(row["is_programme_shell"])),
            -int(row["priority"]),
            normalize_name(str(row["tranche_name"])),
        )
    )
    output_path = settings.manual_dir / "review_queue.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "priority",
                "tranche_name",
                "record_type",
                "status",
                "issues",
                "recommended_actions",
                "sponsor_name",
                "issuer_name",
                "peril_codes",
                "region_codes",
                "maturity_date",
                "source_url",
            ],
        )
        writer.writeheader()
        for row in queue_rows[:limit]:
            row = dict(row)
            row.pop("is_programme_shell", None)
            writer.writerow(row)
    return str(output_path)
