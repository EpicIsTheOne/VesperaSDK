"""Exercise the real loopback UI server in a separate owned process."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import httpx


class RuntimeTests(unittest.TestCase):
    def test_cli_ui_share_session_configuration_and_local_authentication(self):
        calls = []

        class Proxy(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                calls.append((self.path, self.headers.get('Authorization')))
                body = b'{"data":[{"id":"fixture-model"}]}'
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)

        proxy = ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
        thread = threading.Thread(target=proxy.serve_forever, daemon=True); thread.start()
        with tempfile.TemporaryDirectory() as directory:
            source = "from vespera_connector.config import Store,MemoryVault; from vespera_connector.runtime import serve; import sys; serve(Store(sys.argv[1],MemoryVault()))"
            process = subprocess.Popen([sys.executable, '-c', source, directory], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                path = Path(directory, 'runtime.json')
                deadline = time.monotonic()+15
                while not path.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertTrue(path.exists(), 'Runtime did not create its control endpoint')
                endpoint = json.loads(path.read_text())
                base = f"http://127.0.0.1:{endpoint['port']}"
                auth = {'Authorization': 'Bearer ' + endpoint['token']}
                with httpx.Client(base_url=base, timeout=5, trust_env=False) as client:
                    self.assertEqual(client.get('/api/status').status_code, 401)
                    self.assertEqual(client.get('/api/status', headers={**auth, 'Origin': 'https://evil.invalid'}).status_code, 403)
                    self.assertEqual(client.get('/api/status', headers={**auth, 'Host': 'evil.invalid'}).status_code, 403)
                    response = client.post('/api/configure', headers=auth, json={'local_url': f'http://127.0.0.1:{proxy.server_port}/v1', 'api_key': 'fixture-local-secret'})
                    self.assertEqual(response.status_code, 200, response.text)
                    status = client.get('/api/status', headers=auth).json()
                    self.assertTrue(status['has_api_key'])
                    self.assertTrue(status['session_only'])
                    self.assertNotIn('fixture-local-secret', json.dumps(status))
                    self.assertFalse(Path(directory, 'config.json').exists())
                    result = client.post('/api/check', headers=auth, json={})
                    self.assertEqual(result.json()['models'], ['fixture-model'])
                    self.assertEqual(calls, [('/v1/models', 'Bearer fixture-local-secret')])
                    self.assertEqual(client.post('/api/configure', headers=auth, json={'local_url': 'http://192.168.1.5/v1'}).status_code, 400)
                    self.assertEqual(client.get('/').status_code, 200)
                    self.assertEqual(client.post('/api/shutdown', headers=auth, json={}).status_code, 200)
                process.wait(timeout=10)
                self.assertEqual(process.returncode, 0, process.stderr.read().decode())
            finally:
                if process.poll() is None: process.terminate(); process.wait(timeout=5)
                process.stdout.close(); process.stderr.close()
                proxy.shutdown(); proxy.server_close(); thread.join()


if __name__ == '__main__': unittest.main()
