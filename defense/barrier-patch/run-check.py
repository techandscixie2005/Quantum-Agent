"""Capture exact argv, content version, dependencies and exit status per check."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[2]
label, cwd, *command = sys.argv[1:]
out = root / 'defense/barrier-patch/results' / label
out.mkdir(parents=True, exist_ok=False)
files = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=root).decode().split('\0')
# Include untracked implementation and fixtures; exclude generated evidence/logs
# from source identity to avoid recursive manifests. Their own hashes are below.
files = sorted(set(f for f in files if f and (root/f).is_file() and not f.startswith(('docs/implementation/artifacts/', '.demo/')) and (not f.startswith('defense/') or (root/f).suffix in ('.py', '.ts'))))
manifest = {f: hashlib.sha256((root/f).read_bytes()).hexdigest() for f in files}
version = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
metadata = {'argv': command, 'cwd': str(root/cwd), 'started': datetime.now(timezone.utc).isoformat(),
            'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root).decode().strip(),
            'source_version': version, 'files': manifest,
            'dependencies': sorted(f'{d.metadata["Name"]}=={d.version}' for d in importlib.metadata.distributions()),
            'course_edition': '64077260-0470-5742-8424-c73697d9f399',
            'course_evidence_sha256': hashlib.sha256((root/'defense/readiness-evidence/database.json').read_bytes()).hexdigest(),
            'offline_guard_sha256': hashlib.sha256((root/'defense/barrier-patch/offline/sitecustomize.py').read_bytes()).hexdigest(),
            'python': sys.version, 'model_evidence': False}
env = dict(os.environ, QA_LIVE_INFRA='0', QA_LIVE_MODEL='0', PYTHONPATH=str(root/'defense/barrier-patch/offline')+os.pathsep+str(root/'services/api'))
with (out/'output.txt').open('w') as log:
    result = subprocess.run(command, cwd=root/cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
metadata.update(exit_code=result.returncode, ended=datetime.now(timezone.utc).isoformat())
metadata['source_unchanged_at_end'] = all((root/f).is_file() and hashlib.sha256((root/f).read_bytes()).hexdigest() == digest for f, digest in manifest.items())
metadata['log_sha256'] = hashlib.sha256((out/'output.txt').read_bytes()).hexdigest()
(out/'version.json').write_text(json.dumps(metadata, indent=2))
print(json.dumps({'label': label, 'exit_code': result.returncode, 'version': version}))
print((out/'output.txt').read_text()[-6500:])
sys.exit(result.returncode)
