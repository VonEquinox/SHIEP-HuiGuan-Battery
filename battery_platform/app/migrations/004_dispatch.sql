CREATE TABLE IF NOT EXISTS dispatch_resources (
 id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL DEFAULT '{}',
 version INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL,
 updated_by INTEGER REFERENCES users(id));
INSERT OR IGNORE INTO dispatch_resources(id,payload,updated_at) VALUES(1,'{}','');
CREATE TABLE IF NOT EXISTS dispatch_requirements (
 order_id INTEGER PRIMARY KEY REFERENCES orders(id) ON DELETE CASCADE,
 required_qualifications TEXT NOT NULL DEFAULT '[]',
 duration_minutes INTEGER NOT NULL DEFAULT 60 CHECK(duration_minutes>0),
 due_at TEXT, severity TEXT NOT NULL DEFAULT 'routine' CHECK(severity IN ('routine','high','critical')),
 hard_deadline INTEGER NOT NULL DEFAULT 0 CHECK(hard_deadline IN (0,1)),
 predecessors TEXT NOT NULL DEFAULT '[]', required_tools TEXT NOT NULL DEFAULT '{}',
 release_at TEXT, version INTEGER NOT NULL DEFAULT 1,
 updated_at TEXT NOT NULL, updated_by INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS dispatch_plans (
 id INTEGER PRIMARY KEY, job_id INTEGER UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
 status TEXT NOT NULL DEFAULT 'QUEUED', version INTEGER NOT NULL DEFAULT 1,
 horizon_start TEXT NOT NULL, horizon_minutes INTEGER NOT NULL,
 input_snapshot TEXT NOT NULL, input_hash TEXT NOT NULL, result TEXT,
 created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 confirmed_by INTEGER REFERENCES users(id), confirmed_at TEXT,
 confirmed_version INTEGER, confirm_key TEXT, confirm_request_hash TEXT,
 UNIQUE(confirmed_by,confirm_key));
CREATE TABLE IF NOT EXISTS dispatch_assignments (
 id INTEGER PRIMARY KEY, plan_id INTEGER NOT NULL REFERENCES dispatch_plans(id) ON DELETE CASCADE,
 order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
 engineer_id INTEGER NOT NULL REFERENCES users(id), start_at TEXT NOT NULL,
 end_at TEXT NOT NULL, order_version INTEGER NOT NULL,
 UNIQUE(plan_id,order_id));
CREATE INDEX IF NOT EXISTS dispatch_assignment_engineer ON dispatch_assignments(engineer_id,start_at,end_at);
