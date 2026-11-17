import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from vespera_connector.config import Store, validate_local, validate_site
from vespera_connector.relay import dispatch, relay_once


class Vault:
    def __init__(self): self.values = {}
    def get_password(self, service, name): return self.values.get((service, name))
    def set_password(self, service, name, value): self.values[service, name] = value
    def delete_password(self, service, name): self.values.pop((service, name), None)


class ConnectorTests(unittest.TestCase):
    def test_only_loopback_is_allowed(self):
        for value in ['http://127.0.0.1:8317/v1', 'http://[::1]:8317/v1', 'http://localhost:8317/v1']:
            self.assertEqual(validate_local(value), value)
        for value in ['http://192.168.1.1/v1', 'http://example.com/v1', 'http://localhost.evil/v1', 'http://key@localhost/v1', 'http://localhost/v1?key=x']:
            with self.assertRaises(ValueError): validate_local(value)

    def test_remote_site_requires_https_and_preserves_beta(self):
        self.assertEqual(validate_site('https://vespera.ephixd.com/beta'), 'https://vespera.ephixd.com/beta/')
        with self.assertRaises(ValueError): validate_site('http://vespera.ephixd.com/')

    def test_credentials_are_not_written_to_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Vault(); store = Store(directory, vault)
            store.configure({'api_key': 'private-local-key'})
            store.set_credential('bridge-token', 'private-device-token')
            self.assertNotIn('private-', store.path.read_text())
            self.assertEqual(Store(directory, vault).credential('proxy-key'), 'private-local-key')
            store.configure({'local_url': 'http://127.0.0.1:9000/v1'})
            self.assertEqual(store.credential('proxy-key'), 'private-local-key')

    def test_proxy_key_never_sent_to_vespera_and_no_uncertain_replay(self):
        calls = []
        def handler(request):
            calls.append(request)
            if request.url.path.endswith('/poll'):
                return httpx.Response(200, json={'id': 'request1', 'request': {'operation': 'completion', 'payload': {'model': 'test'}}})
            if request.url.host == '127.0.0.1':
                self.assertEqual(request.headers['Authorization'], 'Bearer local-secret')
                raise httpx.ReadError('lost provider response')
            self.assertEqual(request.headers['Authorization'], 'Bearer device-secret')
            self.assertNotIn(b'local-secret', request.content)
            return httpx.Response(409)
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory, Vault())
            store.configure({'api_key': 'local-secret'})
            store.set_credential('bridge-token', 'device-secret')
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(httpx.HTTPStatusError): relay_once(client, store)
            self.assertEqual(sum(r.url.host == '127.0.0.1' for r in calls), 1)
            self.assertEqual(len(calls), 3)

    def test_bounded_response_and_unknown_operation(self):
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b'x'*500001))) as client:
            with self.assertRaises(ValueError): dispatch(client, 'http://127.0.0.1:8317/v1', '', {'operation': 'models'})
            with self.assertRaises(ValueError): dispatch(client, 'http://127.0.0.1:8317/v1', '', {'operation': 'execute', 'payload': {}})


if __name__ == '__main__': unittest.main()
