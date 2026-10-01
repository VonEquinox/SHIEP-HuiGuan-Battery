CREATE TABLE IF NOT EXISTS carbon_factors (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL, version TEXT NOT NULL,
 payload TEXT NOT NULL, content_hash TEXT NOT NULL, created_by INTEGER REFERENCES users(id),
 created_at TEXT NOT NULL, UNIQUE(code,version)
);
CREATE TABLE IF NOT EXISTS policy_benefits (
 id INTEGER PRIMARY KEY, rule_id TEXT NOT NULL, version TEXT NOT NULL,
 payload TEXT NOT NULL, content_hash TEXT NOT NULL, created_by INTEGER REFERENCES users(id),
 created_at TEXT NOT NULL, UNIQUE(rule_id,version)
);
CREATE TABLE IF NOT EXISTS carbon_scenarios (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL,
 payload TEXT NOT NULL, content_hash TEXT NOT NULL, created_by INTEGER REFERENCES users(id),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS carbon_results (
 id INTEGER PRIMARY KEY, scenario_id INTEGER NOT NULL REFERENCES carbon_scenarios(id),
 scenario_version INTEGER NOT NULL, job_id INTEGER NOT NULL UNIQUE REFERENCES jobs(id),
 input_hash TEXT NOT NULL, input_snapshot TEXT NOT NULL, payload TEXT NOT NULL,
 created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS carbon_activities (
 id INTEGER PRIMARY KEY, result_id INTEGER NOT NULL REFERENCES carbon_results(id),
 candidate_id TEXT NOT NULL, ordinal INTEGER NOT NULL, factor_id INTEGER NOT NULL REFERENCES carbon_factors(id),
 payload TEXT NOT NULL, UNIQUE(result_id,candidate_id,ordinal)
);
CREATE TABLE IF NOT EXISTS carbon_ledger (
 id INTEGER PRIMARY KEY, result_id INTEGER NOT NULL REFERENCES carbon_results(id),
 candidate_id TEXT NOT NULL, claim_type TEXT NOT NULL CHECK(claim_type IN ('activity_emission','product_footprint','comparative_avoided')),
 basis TEXT NOT NULL CHECK(basis IN ('projected','settled')), review_status TEXT NOT NULL CHECK(review_status IN ('pending','reviewed','rejected')),
 provenance TEXT NOT NULL CHECK(provenance IN ('real','synthetic','unverified')),
 accounting_period TEXT NOT NULL, boundary_key TEXT NOT NULL, gas_scope TEXT NOT NULL,
 emission_kg REAL NOT NULL, evidence_reference TEXT NOT NULL,
 reversal_of INTEGER UNIQUE REFERENCES carbon_ledger(id), correction_reason TEXT,
 created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS carbon_ledger_claim_once
 ON carbon_ledger(result_id,candidate_id,claim_type,basis) WHERE reversal_of IS NULL;
