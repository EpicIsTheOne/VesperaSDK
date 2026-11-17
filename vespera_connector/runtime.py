"""One local background process for CLI and browser-based settings."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import platform
import sys
import threading
import time

import httpx

from .config import private_write, MemoryVault
from .relay import dispatch, relay_once


class Runtime:
    def __init__(self, store):
        self.store = store
        self.stop = threading.Event()
        self.lock = threading.RLock()
        self.pairing = None
        self.device_code = None
        self.next_poll = 0
        self.state = 'ready'
        self.error = ''

    def status(self):
        with self.lock:
            return {'configured': bool(self.store.data.get('configured')), 'vespera_url': self.store.data['vespera_url'],
                    'local_url': self.store.data['local_url'], 'has_api_key': bool(self.store.credential('proxy-key')),
                    'paired': bool(self.store.data.get('provider_id')), 'provider_id': self.store.data.get('provider_id'),
                    'running': True, 'state': self.state, 'error': self.error, 'pairing': self.pairing,
                    'session_only': isinstance(self.store.vault, MemoryVault),
                    'autostart_available': bool(getattr(sys, 'frozen', False)) and not isinstance(self.store.vault, MemoryVault),
                    'autostart_enabled': bool(self.store.data.get('autostart_enabled'))}

    def setup(self):
        with self.lock:
            if self.store.data.get('provider_id'):
                raise ValueError('Already paired. Disconnect before pairing again.')
            self.store.check_vault()
            with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
                response = client.post(self.store.data['vespera_url'].rstrip('/') + '/api/provider-bridges/device/start',
                                       json={'name': platform.node()[:80] or 'My computer'})
                response.raise_for_status()
                value = response.json()
            # Approval URLs must remain on the configured Vespera origin and channel.
            expected = self.store.data['vespera_url'].rstrip('/') + '/connect'
            if value.get('verification_uri') != expected or not value.get('verification_uri_complete', '').startswith(expected + '?'):
                raise ValueError('The server returned an unexpected pairing address.')
            self.device_code = value.pop('device_code')
            self.pairing = {**value, 'expires_at': time.time() + value['expires_in']}
            self.next_poll = time.monotonic()
            self.state, self.error = 'awaiting_approval', ''
            return self.pairing

    def disconnect(self):
        with self.lock:
            token = self.store.credential('bridge-token')
            if token:
                with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
                    response = client.delete(self.store.data['vespera_url'].rstrip('/') + '/api/provider-bridges/device/session',
                                             headers={'Authorization': 'Bearer ' + token})
                    if response.status_code not in (401, 403):
                        response.raise_for_status()
            self.store.forget()
            self.pairing = self.device_code = None
            self.state, self.error = 'ready', ''

    def worker(self):
        with httpx.Client(timeout=310, follow_redirects=False, trust_env=False) as client:
            while not self.stop.is_set():
                try:
                    with self.lock:
                        device = self.device_code
                        paired = bool(self.store.data.get('provider_id'))
                    if device:
                        if time.time() >= self.pairing['expires_at']:
                            with self.lock:
                                self.device_code = self.pairing = None
                                self.state, self.error = 'expired', 'Pairing expired. Start again.'
                        elif time.monotonic() >= self.next_poll:
                            self.next_poll = time.monotonic() + 5
                            response = client.post(self.store.data['vespera_url'].rstrip('/') + '/api/provider-bridges/device/token', json={'device_code': device})
                            response.raise_for_status()
                            value = response.json()
                            with self.lock:
                                if device != self.device_code:
                                    continue
                                if value['status'] == 'connected':
                                    self.store.set_credential('bridge-token', value['token'])
                                    self.store.data['provider_id'] = value['provider_id']
                                    self.store.save()
                                    self.pairing = self.device_code = None
                                    self.state, self.error = 'connected', ''
                                elif value['status'] in ('expired_token', 'access_denied'):
                                    self.state = value['status']
                                    self.error = value.get('error', 'Pairing expired or was declined. Start again.')
                                    self.pairing = self.device_code = None
                                elif value['status'] == 'slow_down':
                                    self.next_poll += 5
                    elif paired:
                        relay_once(client, self.store)
                        self.state, self.error = 'connected', ''
                        continue
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in (401, 403):
                        self.state, self.error = 'revoked', 'Vespera rejected this connector. Disconnect and pair again.'
                        self.stop.wait(10)
                    else:
                        self.state, self.error = 'reconnecting', 'Connection interrupted. Reconnecting without replaying requests.'
                        self.stop.wait(3)
                except (httpx.HTTPError, ValueError, KeyError, OSError):
                    self.state, self.error = 'reconnecting', 'Connection or credential storage unavailable. Check settings; no generation is replayed.'
                    self.stop.wait(3)
                self.stop.wait(.25)


def serve(store):
    # An OS file lock prevents two services from claiming the same provider.
    store.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    lockfile = open(store.directory / 'runtime.lock', 'a+b')
    lockfile.seek(0)
    if sys.platform == 'win32':
        import msvcrt
        if not lockfile.read(1):
            lockfile.write(b'0'); lockfile.flush()
        lockfile.seek(0)
        msvcrt.locking(lockfile.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
    runtime, token = Runtime(store), secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log prompts, keys, authorization headers, or pairing codes.

        def send(self, status, value, html=False):
            encoded = value if html else json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(encoded)

        def authorized(self):
            # Validate Host as well as bearer to resist DNS rebinding.
            if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                self.send(403, {'error': 'Invalid local host.'}); return False
            origin = self.headers.get('Origin')
            if origin and origin != f'http://127.0.0.1:{self.server.server_port}':
                self.send(403, {'error': 'Invalid local origin.'}); return False
            if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                self.send(401, {'error': 'Open settings through vespera-connector ui.'}); return False
            return True

        def do_GET(self):
            if self.path == '/':
                self.send(200, Path(__file__).with_name('ui.html').read_bytes(), html=True)
            elif self.authorized():
                if self.path == '/api/status':
                    try:
                        self.send(200, runtime.status())
                    except Exception:
                        self.send(503, {'error': 'Unlock secure credential storage before opening settings.'})
                else:
                    self.send(404, {'error': 'Not found.'})

        def do_POST(self):
            if not self.authorized():
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length < 0 or length > 16384:
                    raise ValueError('Request too large.')
                body = json.loads(self.rfile.read(length) or b'{}')
                if not isinstance(body, dict):
                    raise ValueError('Expected an object.')
                if self.path == '/api/configure':
                    with runtime.lock:
                        store.configure(body)
                    value = runtime.status()
                elif self.path == '/api/setup':
                    value = runtime.setup()
                elif self.path == '/api/disconnect':
                    runtime.disconnect(); value = {'ok': True}
                elif self.path == '/api/check':
                    with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
                        found = dispatch(client, store.data['local_url'], store.credential('proxy-key'), {'operation': 'models'})
                    value = {'ok': True, 'models': [item['id'] for item in found.get('data', []) if isinstance(item.get('id'), str)], 'state': 'proxy_ready'}
                elif self.path == '/api/shutdown':
                    runtime.stop.set(); value = {'ok': True}
                elif self.path == '/api/autostart':
                    from .cli import autostart
                    if isinstance(store.vault, MemoryVault):
                        raise ValueError('Session-only mode cannot save startup credentials.')
                    if not isinstance(body.get('enabled'), bool):
                        raise ValueError('Choose whether startup should be enabled.')
                    autostart(body['enabled'], store.directory)
                    store.data['autostart_enabled'] = body['enabled']
                    store.save()
                    value = {'ok': True}
                else:
                    self.send(404, {'error': 'Not found.'}); return
                self.send(200, value)
            except ValueError as exc:
                self.send(400, {'error': str(exc)})
            except Exception:
                self.send(502, {'error': 'Operation failed. Check the site, local proxy, and secure credential storage.'})

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    server.timeout = .5
    server.socket.settimeout(.5)
    private_write(store.directory / 'runtime.json', {'port': server.server_port, 'token': token})
    worker = threading.Thread(target=runtime.worker, daemon=True)
    worker.start()
    try:
        while not runtime.stop.is_set():
            server.handle_request()
    except KeyboardInterrupt:
        runtime.stop.set()
    finally:
        runtime.stop.set()
        server.server_close()
        (store.directory / 'runtime.json').unlink(missing_ok=True)
        lockfile.close()
