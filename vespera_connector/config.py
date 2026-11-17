"""Nonsecret preferences on disk; credentials exclusively in the OS vault."""
import ipaddress
import json
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import urlsplit

import keyring
from platformdirs import user_config_dir

DEFAULT_SITE = 'https://vespera.ephixd.com/'
DEFAULT_LOCAL = 'http://127.0.0.1:8317/v1'


class MemoryVault:
    """Explicit session-only mode for headless hosts without an OS vault."""
    def __init__(self):
        self.values = {}

    def get_password(self, service, name):
        return self.values.get((service, name))

    def set_password(self, service, name, value):
        self.values[service, name] = value

    def delete_password(self, service, name):
        self.values.pop((service, name), None)


def validate_local(value):
    parsed = urlsplit(value)
    try:
        local = parsed.hostname == 'localhost' or ipaddress.ip_address(parsed.hostname or '').is_loopback
        port = parsed.port
    except ValueError:
        local = False
    if not local or parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path.rstrip('/') != '/v1':
        raise ValueError('Use a loopback CLIProxy /v1 address, such as http://127.0.0.1:8317/v1.')
    return value.rstrip('/')


def validate_site(value):
    parsed = urlsplit(value)
    # HTTP is only for isolated local development, never a remote server.
    if (parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1'))) or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Use your Vespera HTTPS site address.')
    return value.rstrip('/') + '/'


def private_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + '.' + secrets.token_hex(5))
    descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class Store:
    def __init__(self, directory=None, vault=None):
        self.directory = Path(directory or user_config_dir('VesperaConnector', 'Ephix'))
        self.path = self.directory / 'config.json'
        self.vault = vault or keyring
        self.data = json.loads(self.path.read_text('utf-8')) if self.path.exists() else {}
        self.data.setdefault('identity', secrets.token_hex(16))
        self.data.setdefault('vespera_url', DEFAULT_SITE)
        self.data.setdefault('local_url', DEFAULT_LOCAL)
        if isinstance(self.vault, MemoryVault):
            self.data.pop('provider_id', None)

    def save(self):
        if isinstance(self.vault, MemoryVault):
            return
        private_write(self.path, self.data)

    def credential(self, name):
        self.check_vault()
        return self.vault.get_password('VesperaConnector:' + self.data['identity'], name) or ''

    def check_vault(self):
        if self.vault is not keyring:
            return
        backend = keyring.get_keyring()
        module = type(backend).__module__
        allowed = ('keyring.backends.Windows',) if sys.platform == 'win32' else ('keyring.backends.SecretService', 'keyring.backends.kwallet')
        if not module.startswith(allowed):
            raise ValueError('Secure credential storage is unavailable. On Linux, unlock/install Secret Service or KWallet. Plaintext credential storage is not supported.')

    def set_credential(self, name, value):
        self.check_vault()
        service = 'VesperaConnector:' + self.data['identity']
        if value:
            self.vault.set_password(service, name, value)
        else:
            try:
                self.vault.delete_password(service, name)
            except keyring.errors.PasswordDeleteError:
                pass

    def configure(self, values):
        site = validate_site(values.get('vespera_url', self.data['vespera_url']))
        local = validate_local(values.get('local_url', self.data['local_url']))
        if site != self.data['vespera_url'] and self.data.get('provider_id'):
            raise ValueError('Disconnect before changing the Vespera site.')
        if 'api_key' in values:
            self.set_credential('proxy-key', values['api_key'])
        self.data.update(vespera_url=site, local_url=local, configured=True)
        self.save()

    def forget(self):
        self.set_credential('bridge-token', '')
        self.data.pop('provider_id', None)
        self.save()
