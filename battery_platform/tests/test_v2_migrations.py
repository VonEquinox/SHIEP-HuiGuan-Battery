"""Upgrade a genuine V1 database copy; verify backups and atomic failure."""
import os
from pathlib import Path
import subprocess
import sys


def test_upgrade_preserves_v1_and_failed_chain_rolls_back(tmp_path):
    program = r'''
import os, sqlite3, shutil
from pathlib import Path
from app.db import SCHEMA_SQL, initialize, engine
from app.migrations import migrate
runtime=Path(os.environ["BATTERY_RUNTIME"])
runtime.mkdir(exist_ok=True)
database=runtime/"battery.db"
with sqlite3.connect(database) as c:
    c.executescript(SCHEMA_SQL)
    c.execute("INSERT INTO users(id,username,display_name,password_hash,role,created_at) VALUES(1,'v1-user','V1','test-hash','admin','2026-09-25')")
    c.execute("INSERT INTO assets(id,code,name,kind,installation_id,created_at) VALUES(1,'v1-cell','Original','cell','original-installation','2026-09-25')")
initialize()
with sqlite3.connect(database) as c:
    assert c.execute("SELECT installation_id FROM assets WHERE id=1").fetchone()[0]=='original-installation'
    assert c.execute("SELECT username FROM users WHERE id=1").fetchone()[0]=='v1-user'
    applied=c.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    assert len(applied)>=3
    assert c.execute("PRAGMA integrity_check").fetchone()[0]=='ok'
backups=list((runtime/"backups").glob('pre-v2-migration-*.sqlite'))
assert backups
with sqlite3.connect(backups[0]) as c:
    assert c.execute("SELECT username FROM users WHERE id=1").fetchone()[0]=='v1-user'
before=len(backups)
initialize()
assert len(list((runtime/"backups").glob('pre-v2-migration-*.sqlite')))==before
scripts=runtime/'test-migrations'; scripts.mkdir()
source=Path('app/migrations')
for p in source.glob('[0-9][0-9][0-9]_*.sql'): shutil.copy(p,scripts/p.name)
(scripts/'090_failure.sql').write_text('CREATE TABLE migration_must_rollback(id INTEGER);\nINSERT INTO nonexistent_migration_table VALUES(1);\n')
try: migrate(scripts)
except Exception: pass
else: raise AssertionError('invalid migration unexpectedly succeeded')
with sqlite3.connect(database) as c:
    assert c.execute("SELECT name FROM sqlite_master WHERE name='migration_must_rollback'").fetchone() is None
    assert c.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()==applied
    assert c.execute("PRAGMA foreign_key_check").fetchall()==[]
first=sorted(scripts.glob('[0-9][0-9][0-9]_*.sql'))[0]
first.write_text(first.read_text()+'\n-- checksum drift\n')
try: migrate(scripts)
except RuntimeError as e: assert 'modified' in str(e)
else: raise AssertionError('applied migration drift went unnoticed')
print('v1-preserved backups-verified rollback-verified checksum-drift-rejected')
'''
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-c", program], cwd=root,
        env={**os.environ, "BATTERY_RUNTIME": str(tmp_path / "runtime")},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "rollback-verified" in result.stdout
