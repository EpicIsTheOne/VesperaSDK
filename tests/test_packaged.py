"""Optional exact-binary smoke, enabled only with an owned candidate path."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import httpx


@unittest.skipUnless(os.getenv('VESPERA_CONNECTOR_TEST_BINARY'), 'No packaged candidate selected')
class PackagedTests(unittest.TestCase):
    def check_binary(self, session):
        binary = str(Path(os.environ['VESPERA_CONNECTOR_TEST_BINARY']).resolve())
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, 'LOCALAPPDATA': directory, 'APPDATA': directory, 'XDG_CONFIG_HOME': directory}
            # The candidate owns this temporary configuration, never the user's normal connector.
            process = subprocess.Popen([binary, 'run', '--config-dir', directory] + (['--session'] if session else []), env=env,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic()+30
                paths = []
                while not paths and time.monotonic()<deadline and process.poll() is None:
                    paths = list(Path(directory).rglob('runtime.json'))
                    time.sleep(.05)
                self.assertTrue(paths, 'Packaged runtime failed to start')
                value = json.loads(paths[0].read_text())
                headers = {'Authorization': 'Bearer '+value['token']}
                with httpx.Client(base_url=f"http://127.0.0.1:{value['port']}", timeout=10, trust_env=False) as client:
                    self.assertEqual(client.get('/').status_code, 200)
                    status = client.get('/api/status', headers=headers)
                    self.assertEqual(status.status_code, 200, status.text)
                    self.assertEqual(client.post('/api/configure', headers=headers, json={'api_key':'fixture-packaged-key'}).status_code, 200)
                    self.assertTrue(client.get('/api/status', headers=headers).json()['has_api_key'])
                    self.assertEqual(client.post('/api/configure', headers=headers, json={'api_key':''}).status_code, 200)
                    self.assertFalse(client.get('/api/status', headers=headers).json()['has_api_key'])
                    self.assertEqual(client.post('/api/shutdown', headers=headers, json={}).status_code, 200)
                process.wait(timeout=15)
                self.assertEqual(process.returncode, 0, process.stderr.read().decode(errors='replace'))
            finally:
                if process.poll() is None:
                    if sys.platform == 'win32':
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        process.terminate()
                    process.wait(timeout=10)
                process.stdout.close();process.stderr.close()

    def test_packaged_session_runtime(self):
        self.check_binary(True)

    @unittest.skipUnless(sys.platform == 'win32', 'Linux desktop vault needs an unlocked desktop session')
    def test_packaged_windows_credential_manager(self):
        self.check_binary(False)


if __name__ == '__main__': unittest.main()
