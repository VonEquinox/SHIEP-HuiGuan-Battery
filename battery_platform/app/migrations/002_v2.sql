CREATE TABLE source_manifests (
 id INTEGER PRIMARY KEY, source_id TEXT NOT NULL UNIQUE, landing_url TEXT NOT NULL,
 paper_doi TEXT, license_status TEXT NOT NULL, status TEXT NOT NULL,
 provenance TEXT NOT NULL, manifest TEXT NOT NULL, retrieved_at TEXT, version INTEGER NOT NULL DEFAULT 1);
CREATE INDEX source_manifest_status ON source_manifests(status,provenance,id);
CREATE TABLE raw_segments (
 id INTEGER PRIMARY KEY, source_manifest_id INTEGER NOT NULL REFERENCES source_manifests(id) ON DELETE CASCADE,
 physical_cell_id TEXT NOT NULL, installation_id TEXT, measured_at TEXT, available_at TEXT NOT NULL,
 schema_id TEXT NOT NULL, units TEXT NOT NULL, provenance TEXT NOT NULL, content TEXT NOT NULL);
CREATE INDEX raw_segment_cutoff ON raw_segments(physical_cell_id,installation_id,available_at,id);
CREATE TABLE target_definitions (
 id INTEGER PRIMARY KEY, target_key TEXT NOT NULL UNIQUE, head TEXT NOT NULL,
 unit TEXT NOT NULL, definition TEXT NOT NULL, support_requirements TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE feature_views (
 id INTEGER PRIMARY KEY, source_manifest_id INTEGER REFERENCES source_manifests(id) ON DELETE CASCADE,
 dataset_id INTEGER REFERENCES datasets(id) ON DELETE CASCADE, schema_id TEXT NOT NULL,
 cutoff TEXT NOT NULL, split TEXT NOT NULL, physical_ids TEXT NOT NULL, manifest TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX feature_view_source ON feature_views(source_manifest_id,split,id);
CREATE TABLE prediction_outputs (
 id INTEGER PRIMARY KEY, prediction_id INTEGER NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
 head TEXT NOT NULL, value REAL, unit TEXT NOT NULL, support TEXT NOT NULL,
 distribution_kind TEXT NOT NULL, parameters TEXT NOT NULL, calibration_version TEXT,
 target_definition_id INTEGER REFERENCES target_definitions(id), model_version TEXT NOT NULL,
 reason TEXT NOT NULL, provenance TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(prediction_id,head));
CREATE INDEX prediction_output_head ON prediction_outputs(head,support,id);
CREATE TABLE context_snapshots (
 id INTEGER PRIMARY KEY, context_version INTEGER NOT NULL UNIQUE, parent_id INTEGER REFERENCES context_snapshots(id),
 content TEXT NOT NULL, changes TEXT NOT NULL, state TEXT NOT NULL, validation TEXT NOT NULL,
 provenance TEXT NOT NULL, created_at TEXT NOT NULL, created_by INTEGER REFERENCES users(id) ON DELETE SET NULL);
CREATE UNIQUE INDEX context_one_active ON context_snapshots(state) WHERE state='active';
CREATE TABLE skill_versions (
 id INTEGER PRIMARY KEY, skill_id TEXT NOT NULL, version INTEGER NOT NULL, state TEXT NOT NULL,
 content TEXT NOT NULL, source_trust TEXT NOT NULL, origin TEXT NOT NULL, root_scenario_ids TEXT NOT NULL,
 context_snapshot_id INTEGER REFERENCES context_snapshots(id), created_at TEXT NOT NULL,
 UNIQUE(skill_id,version));
CREATE INDEX skill_state ON skill_versions(skill_id,state,id);
CREATE TABLE memory_items (
 id INTEGER PRIMARY KEY, memory_key TEXT NOT NULL, version INTEGER NOT NULL, state TEXT NOT NULL,
 scope TEXT NOT NULL, trigger TEXT NOT NULL, insight TEXT NOT NULL,
 supporting_case_ids TEXT NOT NULL, counterexamples TEXT NOT NULL, source_trust TEXT NOT NULL,
 origin TEXT NOT NULL, root_scenario_id TEXT, helpful_count INTEGER NOT NULL DEFAULT 0,
 harmful_count INTEGER NOT NULL DEFAULT 0, last_used TEXT, expires_at TEXT,
 context_snapshot_id INTEGER REFERENCES context_snapshots(id), source_feedback_id INTEGER,
 created_at TEXT NOT NULL, UNIQUE(memory_key,version));
CREATE INDEX memory_state_scope ON memory_items(state,origin,id);
CREATE TABLE incident_groups (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL,
 relation_type TEXT NOT NULL, reason TEXT NOT NULL, evidence TEXT NOT NULL,
 window_start TEXT NOT NULL, window_end TEXT NOT NULL, provenance TEXT NOT NULL,
 parent_group_id INTEGER REFERENCES incident_groups(id), primary_alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
 version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, created_by INTEGER REFERENCES users(id) ON DELETE SET NULL);
CREATE INDEX incident_group_status ON incident_groups(status,provenance,id);
CREATE TABLE incident_members (
 group_id INTEGER NOT NULL REFERENCES incident_groups(id) ON DELETE CASCADE,
 asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE, installation_id TEXT NOT NULL,
 alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL, state TEXT NOT NULL DEFAULT 'active',
 evidence TEXT NOT NULL, PRIMARY KEY(group_id,asset_id));
CREATE INDEX incident_member_asset ON incident_members(asset_id,installation_id,group_id);
CREATE TABLE diagnostic_sessions (
 id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
 installation_id TEXT NOT NULL, incident_group_id INTEGER REFERENCES incident_groups(id),
 status TEXT NOT NULL, round INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE);
CREATE INDEX diagnostic_asset ON diagnostic_sessions(asset_id,installation_id,status,id);
CREATE TABLE agent_runs (
 id INTEGER PRIMARY KEY, job_id INTEGER UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
 session_id INTEGER NOT NULL REFERENCES diagnostic_sessions(id) ON DELETE CASCADE,
 asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE, installation_id TEXT NOT NULL,
 visible_cutoff TEXT NOT NULL, round INTEGER NOT NULL, context_snapshot_id INTEGER NOT NULL REFERENCES context_snapshots(id),
 status TEXT NOT NULL, agent_version TEXT NOT NULL, request TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1, error TEXT, created_at TEXT NOT NULL, finished_at TEXT);
CREATE INDEX agent_run_asset ON agent_runs(asset_id,installation_id,status,id);
CREATE TABLE agent_reports (
 id INTEGER PRIMARY KEY, agent_run_id INTEGER NOT NULL UNIQUE REFERENCES agent_runs(id) ON DELETE CASCADE,
 session_id INTEGER NOT NULL REFERENCES diagnostic_sessions(id) ON DELETE CASCADE,
 asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE, installation_id TEXT NOT NULL,
 round INTEGER NOT NULL, report_version INTEGER NOT NULL, context_snapshot_id INTEGER NOT NULL REFERENCES context_snapshots(id),
 report TEXT NOT NULL, tool_trace TEXT NOT NULL, provenance TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(session_id,report_version));
CREATE INDEX report_session ON agent_reports(session_id,round,id);
CREATE TABLE work_proposals (
 id INTEGER PRIMARY KEY, report_id INTEGER NOT NULL REFERENCES agent_reports(id) ON DELETE CASCADE,
 session_id INTEGER NOT NULL REFERENCES diagnostic_sessions(id) ON DELETE CASCADE,
 incident_group_id INTEGER REFERENCES incident_groups(id), primary_alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
 title TEXT NOT NULL, status TEXT NOT NULL, asset_ids TEXT NOT NULL, installation_ids TEXT NOT NULL,
 allowed_tests TEXT NOT NULL, required_tests TEXT NOT NULL, required_qualifications TEXT NOT NULL,
 duration_minutes INTEGER NOT NULL, max_rounds INTEGER NOT NULL, due_at TEXT, expires_at TEXT,
 severity TEXT NOT NULL, predecessors TEXT NOT NULL, required_tools TEXT NOT NULL,
 content TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, approved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
 approved_version INTEGER, approved_content TEXT, approval_hash TEXT, order_id INTEGER UNIQUE REFERENCES orders(id) ON DELETE SET NULL);
CREATE INDEX proposal_pending ON work_proposals(status,severity,id);
CREATE TABLE order_assets (
 order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
 asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE, installation_id TEXT NOT NULL,
 PRIMARY KEY(order_id,asset_id));
CREATE INDEX order_asset_identity ON order_assets(asset_id,installation_id,order_id);
CREATE TABLE order_alert_links (
 order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
 alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
 PRIMARY KEY(order_id,alert_id));
CREATE TABLE inspection_rounds (
 id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
 session_id INTEGER NOT NULL REFERENCES diagnostic_sessions(id) ON DELETE CASCADE,
 round INTEGER NOT NULL, status TEXT NOT NULL, authorized_tests TEXT NOT NULL,
 required_tests TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, submitted_at TEXT, submitted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
 UNIQUE(order_id,round));
CREATE INDEX inspection_round_status ON inspection_rounds(status,order_id,round);
CREATE TABLE inspection_observations (
 id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
 session_id INTEGER NOT NULL REFERENCES diagnostic_sessions(id) ON DELETE CASCADE,
 asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE, installation_id TEXT NOT NULL,
 round INTEGER NOT NULL, test_id TEXT NOT NULL, measured_at TEXT NOT NULL, available_at TEXT NOT NULL,
 instrument_id TEXT NOT NULL, calibration_status TEXT NOT NULL, measurements TEXT NOT NULL,
 observed_symptoms TEXT NOT NULL, performed_actions TEXT NOT NULL,
 confirmed_hypotheses TEXT NOT NULL, excluded_hypotheses TEXT NOT NULL,
 unresolved_items TEXT NOT NULL, free_text TEXT NOT NULL, attachment_ids TEXT NOT NULL,
 assertion_targets TEXT NOT NULL, result TEXT NOT NULL, candidate_facts TEXT NOT NULL,
 extraction_status TEXT NOT NULL, verification_status TEXT NOT NULL DEFAULT 'reported',
 author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, provenance TEXT NOT NULL,
 client_submission_id TEXT NOT NULL, request_hash TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 UNIQUE(author_id,order_id,client_submission_id));
CREATE INDEX inspection_visible ON inspection_observations(asset_id,installation_id,available_at,id);
CREATE TABLE diagnostic_feedback (
 id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES diagnostic_sessions(id) ON DELETE CASCADE,
 report_id INTEGER NOT NULL REFERENCES agent_reports(id) ON DELETE CASCADE,
 order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE, free_text TEXT NOT NULL,
 assertion_targets TEXT NOT NULL, confirmed_hypotheses TEXT NOT NULL, excluded_hypotheses TEXT NOT NULL,
 unresolved_items TEXT NOT NULL, provenance TEXT NOT NULL, candidate_facts TEXT NOT NULL,
 extraction_status TEXT NOT NULL, author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 available_at TEXT NOT NULL, client_submission_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1, UNIQUE(author_id,session_id,client_submission_id));
CREATE INDEX diagnostic_feedback_session ON diagnostic_feedback(session_id,available_at,id);
CREATE TABLE diagnostic_feedback_versions (
 id INTEGER PRIMARY KEY, feedback_id INTEGER NOT NULL REFERENCES diagnostic_feedback(id) ON DELETE CASCADE,
 version INTEGER NOT NULL, content TEXT NOT NULL, author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 note TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(feedback_id,version));
CREATE TABLE inspection_observation_versions (
 id INTEGER PRIMARY KEY, observation_id INTEGER NOT NULL REFERENCES inspection_observations(id) ON DELETE CASCADE,
 version INTEGER NOT NULL, content TEXT NOT NULL, author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 note TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(observation_id,version));
CREATE TABLE evolution_runs (
 id INTEGER PRIMARY KEY, job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE, method TEXT NOT NULL,
 status TEXT NOT NULL, base_context_version INTEGER NOT NULL, result_snapshot_id INTEGER REFERENCES context_snapshots(id),
 source_feedback_ids TEXT NOT NULL, case_ids TEXT NOT NULL, split TEXT NOT NULL,
 changes TEXT NOT NULL, validation TEXT NOT NULL, metrics TEXT NOT NULL,
 provenance TEXT NOT NULL, created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
 created_at TEXT NOT NULL, finished_at TEXT);
CREATE INDEX evolution_status ON evolution_runs(status,split,id);
CREATE TABLE evaluation_runs (
 id INTEGER PRIMARY KEY, evolution_run_id INTEGER NOT NULL REFERENCES evolution_runs(id) ON DELETE CASCADE,
 split TEXT NOT NULL, sample_count INTEGER NOT NULL, metrics TEXT NOT NULL,
 protocol TEXT NOT NULL, budget TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE v2_idempotency (
 actor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, operation TEXT NOT NULL,
 idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(actor_id,operation,idempotency_key));
CREATE TABLE mobile_tokens (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 expires_at REAL NOT NULL, scope TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX mobile_token_expiry ON mobile_tokens(expires_at);
CREATE TABLE v2_model_bindings (
 asset_id INTEGER PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE, installation_id TEXT NOT NULL,
 package_id TEXT NOT NULL, physical_cell_id TEXT NOT NULL, row_index INTEGER NOT NULL,
 feature_manifest_hash TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE);
CREATE TABLE v2_prediction_profiles (
 id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
 asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE, installation_id TEXT NOT NULL,
 physical_cell_id TEXT NOT NULL, source_id TEXT NOT NULL, model_version TEXT NOT NULL,
 support TEXT NOT NULL, profile TEXT NOT NULL, provenance TEXT NOT NULL, target_definition_id INTEGER REFERENCES target_definitions(id),
 available_at TEXT NOT NULL, source_cutoff REAL NOT NULL);
CREATE INDEX v2_profile_visibility ON v2_prediction_profiles(asset_id,installation_id,available_at,id);
