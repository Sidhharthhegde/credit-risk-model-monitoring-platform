PRAGMA foreign_keys = ON;

CREATE TABLE schema_metadata (
    schema_version INTEGER PRIMARY KEY CHECK (schema_version = 1),
    contract_id TEXT NOT NULL,
    contract_sha256 TEXT NOT NULL,
    created_from_phase11_manifest TEXT NOT NULL,
    database_role TEXT NOT NULL CHECK (database_role = 'DERIVED_QUERY_AND_OPERATIONAL_PERSISTENCE_LAYER'),
    authoritative_evidence INTEGER NOT NULL CHECK (authoritative_evidence = 0)
);

CREATE TABLE phase_manifests (
    phase INTEGER PRIMARY KEY CHECK (phase BETWEEN 0 AND 11),
    control_id TEXT NOT NULL,
    manifest_path TEXT NOT NULL UNIQUE,
    manifest_sha256 TEXT NOT NULL UNIQUE,
    approval_state TEXT NOT NULL CHECK (approval_state = 'APPROVED_FROZEN')
);

CREATE TABLE monitoring_runs (
    history_run_id TEXT PRIMARY KEY,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    development_freeze_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    scenario_artifact_id TEXT NOT NULL UNIQUE,
    authorization_state TEXT NOT NULL CHECK (authorization_state IN ('AUTHORIZED','BLOCKED_HARD_GATE','BLOCKED_SOURCE_GOVERNANCE')),
    evidence_scope TEXT NOT NULL CHECK (evidence_scope IN ('LABEL_FREE_ONLY','FULL_OUTCOME_ELIGIBLE','PARTIAL_OUTCOME_EVIDENCE','NOT_ASSESSABLE')),
    overall_model_health TEXT NOT NULL CHECK (overall_model_health IN ('NORMAL','WARNING','CRITICAL','NOT_ASSESSABLE')),
    evidence_type TEXT NOT NULL,
    synthetic_evidence INTEGER NOT NULL CHECK (synthetic_evidence IN (0,1)),
    calendar_interpretation INTEGER NOT NULL CHECK (calendar_interpretation IN (0,1)),
    comparable_longitudinal_run INTEGER NOT NULL CHECK (comparable_longitudinal_run IN (0,1)),
    comparable_run_group_id TEXT,
    period_start TEXT,
    period_end TEXT,
    source_phase11_manifest_sha256 TEXT NOT NULL,
    run_fingerprint TEXT NOT NULL UNIQUE,
    source_created_utc TEXT NOT NULL,
    CHECK ((calendar_interpretation = 0 AND period_start IS NULL AND period_end IS NULL)
        OR (calendar_interpretation = 1 AND period_start IS NOT NULL AND period_end IS NOT NULL)),
    CHECK ((comparable_longitudinal_run = 0 AND comparable_run_group_id IS NULL)
        OR (comparable_longitudinal_run = 1 AND calendar_interpretation = 1 AND comparable_run_group_id IS NOT NULL))
);

CREATE TABLE metric_evidence (
    metric_record_id TEXT PRIMARY KEY,
    history_run_id TEXT NOT NULL REFERENCES monitoring_runs(history_run_id),
    source_run_id TEXT NOT NULL,
    source_phase TEXT NOT NULL,
    component TEXT NOT NULL,
    alert_class TEXT NOT NULL,
    metric_id TEXT NOT NULL,
    metric_role TEXT NOT NULL CHECK (metric_role IN ('DIRECT_ALERT_DRIVER','SUPPORTING_CORROBORATION','DERIVED_ONLY','NON_ALERTING','CONTEXT_ONLY','CONTEXT_ONLY_V1')),
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    metric_value_numeric REAL,
    metric_value_text TEXT,
    metric_severity TEXT NOT NULL CHECK (metric_severity IN ('NORMAL','WARNING','CRITICAL','N/A')),
    evidence_status TEXT NOT NULL CHECK (evidence_status IN ('ELIGIBLE','NOT_ASSESSABLE','INSUFFICIENT_DATA')),
    authority_status TEXT NOT NULL,
    materiality_class TEXT NOT NULL,
    evidence_type TEXT,
    reference_id TEXT,
    source_artifact_path TEXT NOT NULL,
    source_artifact_sha256 TEXT NOT NULL,
    source_row_key TEXT NOT NULL UNIQUE
);

CREATE TABLE alerts (
    alert_id TEXT PRIMARY KEY,
    history_run_id TEXT NOT NULL REFERENCES monitoring_runs(history_run_id),
    source_run_id TEXT NOT NULL,
    alert_key TEXT NOT NULL UNIQUE,
    model_id TEXT NOT NULL,
    alert_class TEXT NOT NULL,
    component TEXT NOT NULL,
    metric_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    metric_value_numeric REAL,
    metric_severity TEXT NOT NULL CHECK (metric_severity IN ('WARNING','CRITICAL')),
    alert_severity TEXT NOT NULL CHECK (alert_severity IN ('WARNING','CRITICAL')),
    reason_code TEXT NOT NULL,
    evidence_status TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    source_phase TEXT NOT NULL,
    source_metric_record_id TEXT NOT NULL REFERENCES metric_evidence(metric_record_id),
    source_artifact_sha256 TEXT NOT NULL,
    opened_source_utc TEXT NOT NULL,
    overall_health_contributor INTEGER NOT NULL CHECK (overall_health_contributor IN (0,1)),
    persistence_eligible INTEGER NOT NULL CHECK (persistence_eligible IN (0,1)),
    repeat_breach_status TEXT NOT NULL,
    production_performance_claim INTEGER NOT NULL CHECK (production_performance_claim = 0)
);

CREATE TABLE alert_events (
    event_id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL REFERENCES alerts(alert_id),
    event_sequence INTEGER NOT NULL CHECK (event_sequence > 0),
    event_type TEXT NOT NULL CHECK (event_type IN ('CREATED','ACKNOWLEDGED','RESOLVED')),
    from_status TEXT CHECK (from_status IN ('OPEN','ACKNOWLEDGED','RESOLVED')),
    to_status TEXT NOT NULL CHECK (to_status IN ('OPEN','ACKNOWLEDGED','RESOLVED')),
    event_utc TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('SYSTEM_IMPORT','LOCAL_DEMO_USER')),
    actor_label TEXT NOT NULL,
    reason TEXT NOT NULL,
    source TEXT NOT NULL,
    UNIQUE(alert_id, event_sequence),
    CHECK (
        (event_type = 'CREATED' AND from_status IS NULL AND to_status = 'OPEN' AND event_sequence = 1)
        OR (event_type = 'ACKNOWLEDGED' AND from_status = 'OPEN' AND to_status = 'ACKNOWLEDGED' AND event_sequence > 1)
        OR (event_type = 'RESOLVED' AND from_status = 'ACKNOWLEDGED' AND to_status = 'RESOLVED' AND event_sequence > 1)
    )
);

CREATE TABLE component_health (
    history_run_id TEXT NOT NULL REFERENCES monitoring_runs(history_run_id),
    component TEXT NOT NULL,
    health_state TEXT NOT NULL CHECK (health_state IN ('NORMAL','WARNING','CRITICAL','NOT_ASSESSABLE','NOT_ASSESSABLE_FOR_ALERT_AGGREGATION')),
    alert_count INTEGER NOT NULL CHECK (alert_count >= 0),
    critical_alert_count INTEGER NOT NULL CHECK (critical_alert_count >= 0),
    warning_alert_count INTEGER NOT NULL CHECK (warning_alert_count >= 0),
    source_artifact_sha256 TEXT NOT NULL,
    PRIMARY KEY(history_run_id, component)
);

CREATE TABLE run_health (
    history_run_id TEXT PRIMARY KEY REFERENCES monitoring_runs(history_run_id),
    authorization_state TEXT NOT NULL,
    evidence_scope TEXT NOT NULL,
    overall_model_health TEXT NOT NULL,
    synthetic_evidence_type TEXT NOT NULL,
    open_alert_count INTEGER NOT NULL CHECK (open_alert_count >= 0),
    critical_alert_count INTEGER NOT NULL CHECK (critical_alert_count >= 0),
    warning_alert_count INTEGER NOT NULL CHECK (warning_alert_count >= 0),
    source_authorization_sha256 TEXT NOT NULL,
    source_evidence_scope_sha256 TEXT NOT NULL,
    source_overall_health_sha256 TEXT NOT NULL
);

CREATE TABLE artifact_lineage (
    lineage_id TEXT PRIMARY KEY,
    phase INTEGER NOT NULL CHECK (phase BETWEEN 0 AND 11),
    artifact_type TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    parent_manifest_sha256 TEXT NOT NULL,
    authoritative INTEGER NOT NULL CHECK (authoritative = 1),
    database_copy_role TEXT NOT NULL CHECK (database_copy_role = 'DERIVED_QUERY_REPRESENTATION'),
    UNIQUE(phase, artifact_path)
);

CREATE INDEX ix_metric_run ON metric_evidence(history_run_id);
CREATE INDEX ix_metric_lookup ON metric_evidence(metric_id, entity_id);
CREATE INDEX ix_alert_run ON alerts(history_run_id);
CREATE INDEX ix_alert_component ON alerts(component, alert_severity);
CREATE INDEX ix_event_alert_sequence ON alert_events(alert_id, event_sequence DESC);

CREATE VIEW v_current_alert_state AS
SELECT alert_id, to_status AS current_status, event_utc AS latest_event_utc,
       actor_type, actor_label, reason, source
FROM (
    SELECT e.*, ROW_NUMBER() OVER (PARTITION BY alert_id ORDER BY event_sequence DESC) AS rank_number
    FROM alert_events e
) ranked
WHERE rank_number = 1;

CREATE VIEW v_open_alerts AS
SELECT a.*, s.current_status, s.latest_event_utc
FROM alerts a JOIN v_current_alert_state s USING(alert_id)
WHERE s.current_status = 'OPEN';

CREATE VIEW v_open_critical_alerts AS
SELECT * FROM v_open_alerts WHERE alert_severity = 'CRITICAL';

CREATE VIEW v_current_run_alert_counts AS
SELECT r.history_run_id,
       SUM(CASE WHEN s.current_status = 'OPEN' THEN 1 ELSE 0 END) AS current_open_alert_count,
       SUM(CASE WHEN s.current_status = 'ACKNOWLEDGED' THEN 1 ELSE 0 END) AS current_acknowledged_alert_count,
       SUM(CASE WHEN s.current_status = 'RESOLVED' THEN 1 ELSE 0 END) AS current_resolved_alert_count,
       SUM(CASE WHEN s.current_status = 'OPEN' AND a.alert_severity = 'WARNING' THEN 1 ELSE 0 END) AS current_open_warning_count,
       SUM(CASE WHEN s.current_status = 'OPEN' AND a.alert_severity = 'CRITICAL' THEN 1 ELSE 0 END) AS current_open_critical_count
FROM monitoring_runs r
LEFT JOIN alerts a USING(history_run_id)
LEFT JOIN v_current_alert_state s USING(alert_id)
GROUP BY r.history_run_id;

CREATE VIEW v_run_summary AS
SELECT r.*,
       h.open_alert_count AS phase11_source_open_alert_count,
       h.critical_alert_count AS phase11_source_critical_alert_count,
       h.warning_alert_count AS phase11_source_warning_alert_count,
       c.current_open_alert_count,
       c.current_acknowledged_alert_count,
       c.current_resolved_alert_count,
       c.current_open_warning_count,
       c.current_open_critical_count
FROM monitoring_runs r
JOIN run_health h USING(history_run_id)
JOIN v_current_run_alert_counts c USING(history_run_id);

CREATE VIEW v_run_component_health AS
SELECT r.scenario_id, r.scenario_artifact_id, c.*
FROM component_health c JOIN monitoring_runs r USING(history_run_id);

CREATE VIEW v_alerts_with_lineage AS
SELECT a.*, s.current_status, l.artifact_path AS source_artifact_path
FROM alerts a
JOIN v_current_alert_state s USING(alert_id)
LEFT JOIN artifact_lineage l ON l.artifact_sha256 = a.source_artifact_sha256
 AND l.phase = CAST(substr(a.source_phase, 7) AS INTEGER);

CREATE VIEW v_metric_evidence_with_lineage AS
SELECT m.*, l.lineage_id
FROM metric_evidence m
LEFT JOIN artifact_lineage l ON l.artifact_sha256 = m.source_artifact_sha256
 AND l.phase = CAST(substr(m.source_phase, 7) AS INTEGER);

CREATE VIEW v_blocked_runs AS
SELECT * FROM v_run_summary
WHERE authorization_state IN ('BLOCKED_HARD_GATE','BLOCKED_SOURCE_GOVERNANCE');

CREATE VIEW v_synthetic_evidence AS
SELECT * FROM v_run_summary WHERE synthetic_evidence = 1;

CREATE VIEW v_comparable_metric_history AS
SELECT m.*, r.comparable_run_group_id, r.period_start, r.period_end
FROM metric_evidence m JOIN monitoring_runs r USING(history_run_id)
WHERE r.calendar_interpretation = 1 AND r.comparable_longitudinal_run = 1;

CREATE TRIGGER immutable_monitoring_runs_update BEFORE UPDATE ON monitoring_runs BEGIN SELECT RAISE(ABORT, 'immutable imported evidence'); END;
CREATE TRIGGER immutable_monitoring_runs_delete BEFORE DELETE ON monitoring_runs BEGIN SELECT RAISE(ABORT, 'immutable imported evidence'); END;
CREATE TRIGGER immutable_metric_update BEFORE UPDATE ON metric_evidence BEGIN SELECT RAISE(ABORT, 'immutable imported evidence'); END;
CREATE TRIGGER immutable_metric_delete BEFORE DELETE ON metric_evidence BEGIN SELECT RAISE(ABORT, 'immutable imported evidence'); END;
CREATE TRIGGER immutable_alert_update BEFORE UPDATE ON alerts BEGIN SELECT RAISE(ABORT, 'immutable imported evidence'); END;
CREATE TRIGGER immutable_alert_delete BEFORE DELETE ON alerts BEGIN SELECT RAISE(ABORT, 'immutable imported evidence'); END;
CREATE TRIGGER append_only_events_update BEFORE UPDATE ON alert_events BEGIN SELECT RAISE(ABORT, 'append-only operational ledger'); END;
CREATE TRIGGER append_only_events_delete BEFORE DELETE ON alert_events BEGIN SELECT RAISE(ABORT, 'append-only operational ledger'); END;
CREATE TRIGGER enforce_alert_event_continuity BEFORE INSERT ON alert_events
BEGIN
    SELECT CASE WHEN NEW.event_sequence != COALESCE((SELECT MAX(event_sequence) FROM alert_events WHERE alert_id = NEW.alert_id), 0) + 1
        THEN RAISE(ABORT, 'alert event sequence must be gapless') END;
    SELECT CASE WHEN NEW.event_sequence > 1 AND NEW.from_status IS NOT
        (SELECT to_status FROM alert_events WHERE alert_id = NEW.alert_id ORDER BY event_sequence DESC LIMIT 1)
        THEN RAISE(ABORT, 'alert event from_status must equal prior to_status') END;
END;
CREATE TRIGGER immutable_component_health_update BEFORE UPDATE ON component_health BEGIN SELECT RAISE(ABORT, 'immutable imported evidence'); END;
CREATE TRIGGER immutable_component_health_delete BEFORE DELETE ON component_health BEGIN SELECT RAISE(ABORT, 'immutable imported evidence'); END;
CREATE TRIGGER immutable_run_health_update BEFORE UPDATE ON run_health BEGIN SELECT RAISE(ABORT, 'immutable imported evidence'); END;
CREATE TRIGGER immutable_run_health_delete BEFORE DELETE ON run_health BEGIN SELECT RAISE(ABORT, 'immutable imported evidence'); END;
CREATE TRIGGER immutable_lineage_update BEFORE UPDATE ON artifact_lineage BEGIN SELECT RAISE(ABORT, 'immutable imported evidence'); END;
CREATE TRIGGER immutable_lineage_delete BEFORE DELETE ON artifact_lineage BEGIN SELECT RAISE(ABORT, 'immutable imported evidence'); END;
CREATE TRIGGER immutable_manifests_update BEFORE UPDATE ON phase_manifests BEGIN SELECT RAISE(ABORT, 'immutable imported evidence'); END;
CREATE TRIGGER immutable_manifests_delete BEFORE DELETE ON phase_manifests BEGIN SELECT RAISE(ABORT, 'immutable imported evidence'); END;
CREATE TRIGGER immutable_schema_metadata_update BEFORE UPDATE ON schema_metadata BEGIN SELECT RAISE(ABORT, 'immutable imported evidence'); END;
CREATE TRIGGER immutable_schema_metadata_delete BEFORE DELETE ON schema_metadata BEGIN SELECT RAISE(ABORT, 'immutable imported evidence'); END;

PRAGMA user_version = 1;
