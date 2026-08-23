"""Generate non-authoritative HTML/PDF summaries exclusively from Phase 12 queries."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from credit_risk_monitoring.dashboard.data_service import DashboardDataService


REPORT_ID = "MONITORING-REPORT-01"


def _metric_dict(service: DashboardDataService, artifact_id: str) -> dict[str, Any]:
    return {row.metric_id: row for row in service.metrics() if row.artifact_id == artifact_id}


def build_snapshot(service: DashboardDataService) -> dict[str, Any]:
    summary = service.snapshot()
    scenarios = service.scenarios()
    m06 = next(row for row in scenarios if row.scenario_id == "SIM-M06")
    m04 = next(row for row in scenarios if row.scenario_id == "SIM-M04")
    m06_metrics = _metric_dict(service, m06.artifact_id)
    m04_metrics = _metric_dict(service, m04.artifact_id)
    selected_m06 = [
        "roc_auc", "performance_ks", "pr_auc_average_precision", "gini", "observed_default_rate",
        "observed_expected_ratio", "brier_score", "log_loss", "recall_default_capture",
        "specificity", "precision", "false_negative_rate",
    ]
    return {
        "report_id": REPORT_ID, "snapshot_utc": datetime.now(timezone.utc).isoformat(),
        "report_role": "DERIVED_GOVERNANCE_PRESENTATION_ARTIFACT", "report_authoritative_evidence": False,
        "model": {"model_id": "XGBT-01", "freeze": "DF-01", "threshold_id": "THRESHOLD-01", "threshold": "PD >= 0.080"},
        "context": {"production_shaped_simulation": True, "real_production_deployment": False, "calendar_interpretation": False},
        "counts": {"metrics": summary.metric_count, "alerts": summary.alert_count, "current_open": summary.open_alert_count,
                   "current_open_critical": summary.open_critical_count, "blocked_runs": summary.blocked_run_count,
                   "synthetic_runs": summary.synthetic_run_count, "comparable_history_rows": summary.comparable_history_count,
                   "phase11_source_alerts": sum(row.phase11_source_open for row in scenarios)},
        "scenarios": [{"artifact_id": row.artifact_id, "scenario_id": row.scenario_id, "label": row.label,
                       "authorization": row.authorization, "evidence_scope": row.evidence_scope,
                       "evidence_type": row.evidence_type, "overall_health": row.overall_health,
                       "current_open": row.current_open, "current_warning": row.current_warning,
                       "current_critical": row.current_critical, "current_acknowledged": row.current_acknowledged,
                       "current_resolved": row.current_resolved} for row in scenarios],
        "m04_prediction_example": {key: {"value": m04_metrics[key].value, "severity": m04_metrics[key].metric_severity}
                                   for key in ["score_psi", "risk_positive_rate_change"] if key in m04_metrics},
        "m06_performance": {key: {"value": m06_metrics[key].value, "severity": m06_metrics[key].metric_severity,
                                    "role": m06_metrics[key].metric_role, "evidence_type": m06_metrics[key].evidence_type}
                            for key in selected_m06 if key in m06_metrics},
        "segments": {"families": 12, "levels": 32, "m06_discrimination_eligible": 21,
                     "m06_discrimination_insufficient": 11, "m06_threshold_eligible": 26,
                     "m06_threshold_insufficient": 6, "evidence_role": "CONTEXT_ONLY_V1"},
        "limitations": ["CND-02 remains OPEN", "Threshold-boundary-density remains CONTROLLED_DEFERRED",
                        "Synthetic outcomes only", "No production deployment", "No empirical production performance",
                        "No external validation", "No fairness or regulatory certification", "No real lending decisions"],
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{value:.4f}" if isinstance(value, float) else str(value)


def _html_report(snapshot: dict[str, Any]) -> str:
    scenario_rows = "".join(
        f"<tr><td>{html.escape(x['label'])}</td><td>{x['authorization']}</td><td>{x['evidence_scope']}</td><td>{x['overall_health']}</td><td>{x['current_open']}</td></tr>"
        for x in snapshot["scenarios"]
    )
    perf_rows = "".join(
        f"<tr><td>{key}</td><td>{_fmt(item['value'])}</td><td>{item['severity']}</td><td>{item['role']}</td></tr>"
        for key, item in snapshot["m06_performance"].items()
    )
    limitations = "".join(f"<li>{html.escape(item)}</li>" for item in snapshot["limitations"])
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Monitoring Report</title><style>
body{{font-family:Arial,sans-serif;color:#172033;margin:0;background:#eef2f6}} main{{max-width:1050px;margin:auto;background:white;padding:48px}}
h1{{color:#0f2747}} h2{{margin-top:34px;border-bottom:2px solid #d8e1ea;padding-bottom:8px}} .banner{{background:#0f2747;color:white;padding:24px;border-radius:10px}}
.warning{{background:#fff4d6;border-left:5px solid #d99a00;padding:14px}} .synthetic{{background:#fde8e8;border-left:5px solid #b42318;padding:14px;font-weight:bold}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}} .card{{background:#f4f7fa;padding:16px;border-radius:8px}} table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{border:1px solid #d8e1ea;padding:8px;text-align:left}} th{{background:#e8eef5}}
.evidence{{border-left:4px solid #2663a5;padding-left:14px}} footer{{margin-top:40px;color:#5d6878;font-size:12px}}</style></head><body><main>
<div class='banner'><h1>Credit Risk Model Monitoring Report</h1><p>MONITORING-REPORT-01 | Snapshot {snapshot['snapshot_utc']}</p><p>Derived governance presentation artifact - frozen source evidence remains authoritative.</p></div>
<div class='warning'><b>Portfolio simulation:</b> DF-01 / XGBT-01 is not represented as deployed or approved for production. M01-M06 are scenarios, not calendar periods.</div>
<h2>1. Executive monitoring summary</h2><div class='cards'><div class='card'><b>Model</b><br>XGBT-01 / DF-01</div><div class='card'><b>Threshold</b><br>PD &gt;= 0.080</div><div class='card'><b>Current open alerts</b><br>{snapshot['counts']['current_open']}</div><div class='card'><b>Open critical</b><br>{snapshot['counts']['current_open_critical']}</div></div>
<h2>2. Scope and evidence basis</h2><p>TRAIN provides the feature/population reference; development validation provides score/performance references; M01-M06 provide simulated production-shaped evidence. M06 outcomes are synthetic.</p>
<h2>3. Data quality and source governance</h2><p class='evidence'><b>Observed evidence:</b> technical scoring and governance authorization are independent. Source-loss can remain technically scoreable while authoritative use is BLOCKED_SOURCE_GOVERNANCE. CND-02 remains OPEN.</p>
<h2>4. Feature drift</h2><p>Feature PSI severity, predictor materiality and alert severity are retained separately. Findings identify investigation areas, not confirmed causes.</p>
<h2>5. Prediction monitoring</h2><p>M04 demonstrates that score PSI and risk-positive-rate change are distinct indicators and are not combined into an invented prediction-drift score.</p><pre>{html.escape(json.dumps(snapshot['m04_prediction_example'], indent=2))}</pre>
<h2>6. Performance and calibration</h2><div class='synthetic'>SYNTHETIC SCENARIO EVIDENCE - NON-EMPIRICAL - NOT EXTERNAL VALIDATION</div><p>M01-M05 remain NOT_ASSESSABLE because outcomes are unavailable. M06 metrics retain direct, supporting and derived roles.</p><table><tr><th>Metric</th><th>Value</th><th>Metric severity</th><th>Role</th></tr>{perf_rows}</table>
<h2>7. Segment and subpopulation evidence</h2><p>12 families and 32 frozen levels. M06 discrimination: 21 eligible, 11 insufficient. Threshold/error rates: 26 eligible, 6 insufficient. Descriptive model-risk evidence does not certify fairness or absence of bias.</p>
<h2>8. Alerts and model-health decisions</h2><table><tr><th>Scenario</th><th>Authorization</th><th>Evidence scope</th><th>Overall health</th><th>Current open</th></tr>{scenario_rows}</table><p>Blocked governance/hard-gate runs retain NOT_ASSESSABLE health and are not converted into CRITICAL model health.</p>
<h2>9. Operational history and lifecycle</h2><p>Phase 11 source alerts: {snapshot['counts']['phase11_source_alerts']}. Current operational state: OPEN {snapshot['counts']['current_open']}. Counts are a point-in-time projection from the append-only event ledger. Comparable longitudinal history rows: 0.</p>
<h2>10. Governance conclusions, limitations and next actions</h2><ul>{limitations}</ul><p><b>Recommended action:</b> preserve conditions, investigate governed alert evidence, and obtain genuinely unseen labelled external/OOT confirmation before external-performance claims.</p>
<footer>MONITORING-REPORT-01 | Non-authoritative presentation artifact | Generated from governed Phase 12 query projections</footer></main></body></html>"""


def _pdf_report(path: Path, snapshot: dict[str, Any]) -> None:
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleCenter", parent=styles["Title"], alignment=TA_CENTER, textColor=colors.HexColor("#0f2747")))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8.5, leading=11))
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=17*mm, bottomMargin=17*mm,
                            title="Credit Risk Model Monitoring Report", author="Sidharth Ravindra Hegde")
    story: list[Any] = [Paragraph("Credit Risk Model Monitoring Report", styles["TitleCenter"]),
        Paragraph("MONITORING-REPORT-01", styles["Heading2"]),
        Paragraph("Derived governance presentation artifact. Frozen source evidence remains authoritative.", styles["BodyText"]), Spacer(1, 8),
        Paragraph("PORTFOLIO SIMULATION - NOT PRODUCTION DEPLOYMENT - M01-M06 ARE NOT CALENDAR PERIODS", styles["Heading3"])]
    sections = [
        ("1. Executive monitoring summary", f"Model XGBT-01; freeze DF-01; threshold THRESHOLD-01 (PD >= 0.080). Current open alerts: {snapshot['counts']['current_open']}; open critical: {snapshot['counts']['current_open_critical']}."),
        ("2. Scope and evidence basis", "TRAIN is the feature/population reference; development validation is the score/performance reference. M01-M06 are simulated evidence. M06 outcomes are synthetic."),
        ("3. Data quality and source governance", "Technical scoring and governance authorization are independent. Source-loss may remain technically scoreable while authoritative use is blocked. CND-02 remains OPEN."),
        ("4. Feature drift", "Feature PSI severity, predictor materiality and alert severity remain separate. Findings are investigation signals and do not establish root cause."),
        ("5. Prediction monitoring", "M04 preserves score PSI and risk-positive-rate change as distinct indicators; no combined prediction-drift score is invented."),
        ("6. Performance and calibration", "SYNTHETIC SCENARIO EVIDENCE - NON-EMPIRICAL - NOT EXTERNAL VALIDATION. M01-M05 remain NOT_ASSESSABLE because outcomes are unavailable."),
        ("7. Segment and subpopulation evidence", "12 families; 32 levels. M06 discrimination: 21 eligible / 11 insufficient. Threshold/error rates: 26 eligible / 6 insufficient. This is not fairness certification."),
        ("8. Alerts and model-health decisions", "Authorization, evidence scope, component health and overall health are independent. Blocked runs retain NOT_ASSESSABLE health."),
        ("9. Operational history and lifecycle", f"Phase 11 source alerts: {snapshot['counts']['phase11_source_alerts']}. Current OPEN: {snapshot['counts']['current_open']}. Comparable longitudinal history rows: 0."),
        ("10. Governance conclusions and limitations", "; ".join(snapshot["limitations"]) + ". External/OOT labelled confirmation remains required for external-performance claims."),
    ]
    for title, body in sections:
        story.append(KeepTogether([Paragraph(title, styles["Heading2"]), Paragraph(body, styles["BodyText"]), Spacer(1, 5)]))
        if title.startswith("6."):
            data = [["Metric", "Value", "Severity", "Role"]] + [[key, _fmt(item["value"]), item["severity"], item["role"]] for key, item in snapshot["m06_performance"].items()]
            table = Table(data, colWidths=[42*mm, 27*mm, 32*mm, 57*mm], repeatRows=1)
            table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#dce6f1")), ("GRID", (0,0), (-1,-1), .4, colors.HexColor("#91a4b7")), ("FONTSIZE", (0,0), (-1,-1), 7), ("VALIGN", (0,0), (-1,-1), "TOP")]))
            story.extend([table, Spacer(1, 6)])
    def footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#5d6878"))
        canvas.drawString(16*mm, 9*mm, "MONITORING-REPORT-01 | Non-authoritative presentation artifact")
        canvas.drawRightString(A4[0] - 16*mm, 9*mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


class MonitoringReportGenerator:
    def __init__(self, project_root: Path, database_path: Path) -> None:
        self.project_root = project_root.resolve()
        self.database_path = database_path.resolve()

    def generate(self, output_dir: Path) -> dict[str, Path]:
        output_dir.mkdir(parents=True, exist_ok=False)
        with DashboardDataService(self.project_root, self.database_path) as service:
            snapshot = build_snapshot(service)
        snapshot_path = output_dir / "monitoring_report_snapshot.json"
        html_path = output_dir / "monitoring_report.html"
        pdf_path = output_dir / "monitoring_report.pdf"
        snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        html_path.write_text(_html_report(snapshot), encoding="utf-8", newline="\n")
        _pdf_report(pdf_path, snapshot)
        return {"snapshot": snapshot_path, "html": html_path, "pdf": pdf_path}
