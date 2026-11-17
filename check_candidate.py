"""Verify and exercise the exact locally built Windows or Linux executable."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
manifest = json.loads((root/'dist'/sys.platform/'SOURCE.json').read_text())
artifact = root/'dist'/sys.platform/manifest['artifact']
assert hashlib.sha256(artifact.read_bytes()).hexdigest() == manifest['sha256'], 'Candidate bytes changed'
for name, digest in manifest['source_inputs'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest() == digest, 'Candidate source changed: '+name
env = {**os.environ, 'VESPERA_CONNECTOR_TEST_BINARY': str(artifact)}
subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(root/'tests')], env=env, check=True)
