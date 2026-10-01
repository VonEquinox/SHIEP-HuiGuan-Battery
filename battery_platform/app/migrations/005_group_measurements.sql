-- Optional, explicit conditions on already-authorized observations. Existing
-- records remain unsupported for numerical grouping until conditions exist.
ALTER TABLE inspection_observations ADD COLUMN comparison_context TEXT NOT NULL DEFAULT '{}';
CREATE INDEX inspection_group_window ON inspection_observations(asset_id,installation_id,measured_at,available_at);
