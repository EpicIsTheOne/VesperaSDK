"""Build a portable executable on the target OS, with no user Python dependency."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
output = root/'dist'/sys.platform
args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--name', 'vespera-connector',
        '--distpath', str(output), '--workpath', str(root/'build'/sys.platform), '--specpath', str(root/'build'/sys.platform),
        '--paths', str(root), '--collect-submodules', 'keyring.backends',
        '--add-data', str(root/'vespera_connector/ui.html') + ':vespera_connector', str(root/'launcher.py')]
subprocess.run(args, cwd=root, check=True)
artifact = output/('vespera-connector.exe' if sys.platform == 'win32' else 'vespera-connector')
digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
(output/'SHA256SUMS').write_text(f'{digest}  {artifact.name}\n')
inputs = [root/'launcher.py', root/'build.py', root/'pyproject.toml']
inputs += [p for p in (root/'vespera_connector').rglob('*') if p.suffix in ('.py', '.html')]
(output/'SOURCE.json').write_text(json.dumps({'artifact': artifact.name, 'sha256': digest, 'platform': sys.platform,
    'python': sys.version.split()[0], 'source_inputs': {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(inputs)}}, indent=2)+'\n')
print(json.dumps({'artifact': str(artifact), 'sha256': digest, 'platform': sys.platform, 'signed': False}, indent=2))
