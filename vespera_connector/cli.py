"""CLI and graphical settings control the same local process and configuration."""
import argparse
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import webbrowser

import httpx

from .config import Store, MemoryVault


def command():
    return [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'vespera_connector']


def control(store, path, body=None):
    value = json.loads((store.directory / 'runtime.json').read_text('utf-8'))
    with httpx.Client(timeout=25, trust_env=False, follow_redirects=False) as client:
        url = f"http://127.0.0.1:{int(value['port'])}/api/{path}"
        auth = {'Authorization': 'Bearer ' + value['token']}
        response = client.get(url, headers=auth) if body is None else client.post(url, headers=auth, json=body)
        response.raise_for_status()
        return response.json()


def ensure_running(store):
    try:
        control(store, 'status')
        return
    except (OSError, ValueError, httpx.HTTPError):
        pass
    store.save()
    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS if sys.platform == 'win32' else 0
    subprocess.Popen(command() + ['run', '--config-dir', str(store.directory)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags, start_new_session=sys.platform != 'win32')
    for _ in range(40):
        try:
            control(store, 'status')
            return
        except (OSError, ValueError, httpx.HTTPError):
            time.sleep(.1)
    raise ValueError('Connector did not start. Run vespera-connector run to see the error.')


def autostart(enable, directory=None):
    args = command() + ['run']
    if directory:
        args += ['--config-dir', str(directory)]
    if not getattr(sys, 'frozen', False):
        raise ValueError('Autostart requires an installed packaged connector, so its executable path remains stable.')
    if sys.platform == 'win32':
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
            if enable:
                winreg.SetValueEx(key, 'VesperaConnector', 0, winreg.REG_SZ, subprocess.list2cmdline(args))
            else:
                try: winreg.DeleteValue(key, 'VesperaConnector')
                except FileNotFoundError: pass
    elif sys.platform.startswith('linux'):
        path = Path.home() / '.config/systemd/user/vespera-connector.service'
        if enable:
            path.parent.mkdir(parents=True, exist_ok=True)
            # systemd specifiers and shell syntax must not reinterpret executable paths.
            escaped = ' '.join('"' + a.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"' for a in args)
            path.write_text('[Unit]\nDescription=Vespera local connector\n[Service]\nExecStart=' + escaped + '\nRestart=on-failure\nRestartSec=5\n[Install]\nWantedBy=default.target\n')
        subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', '--user', 'enable' if enable else 'disable', 'vespera-connector.service'], check=True)
        if not enable:
            path.unlink(missing_ok=True)
    else:
        raise ValueError('Autostart supports Windows and Linux.')


def main():
    parser = argparse.ArgumentParser(description='Connect an existing local CLIProxy to Vespera. No management key is needed.')
    parser.add_argument('action', nargs='?', default='ui', choices=['setup', 'configure', 'status', 'start', 'stop', 'run', 'ui', 'disconnect', 'autostart'])
    parser.add_argument('setting', nargs='?', choices=['enable', 'disable'])
    parser.add_argument('--vespera', help='Vespera HTTPS address, including /beta/ for Beta')
    parser.add_argument('--local-url', help='Loopback CLIProxy /v1 address')
    parser.add_argument('--no-browser', action='store_true', help='Print the pairing link and code for headless setup')
    parser.add_argument('--session', action='store_true', help='Keep credentials only in memory; stay in the foreground. Useful on headless Linux without a keyring.')
    parser.add_argument('--config-dir', help='Use a separate local configuration directory')
    args = parser.parse_args()
    try:
        store = Store(args.config_dir, vault=MemoryVault()) if args.session else Store(args.config_dir)
        session_thread = None
        if args.session and args.action not in ('run', 'setup', 'ui'):
            raise ValueError('--session is supported with setup, ui, or run.')
        if args.session and args.action != 'run':
            import threading
            from .runtime import serve
            try:
                control(store, 'status')
            except (OSError, ValueError, httpx.HTTPError):
                pass
            else:
                raise ValueError('Stop the existing connector before starting a session-only connector.')
            session_thread = threading.Thread(target=serve, args=(store,), daemon=True)
            session_thread.start()
            for _ in range(50):
                try:
                    control(store, 'status'); break
                except (OSError, ValueError, httpx.HTTPError): time.sleep(.1)
            print('Session-only mode: credentials are never saved. Keep this process running; pair again after it stops.')
        if args.action == 'run':
            from .runtime import serve
            serve(store)
        elif args.action == 'autostart':
            if not args.setting:
                raise ValueError('Choose autostart enable or disable.')
            autostart(args.setting == 'enable', store.directory)
            store.data['autostart_enabled'] = args.setting == 'enable'
            store.save()
            print('Startup preference saved. A fresh sign-in is needed to verify startup.')
        elif args.action == 'status':
            try: print(json.dumps(control(store, 'status'), indent=2))
            except (OSError, httpx.HTTPError): print('Connector is stopped.')
        elif args.action == 'stop':
            control(store, 'shutdown', {}); print('Connector is stopping.')
        elif args.action in ('start', 'ui'):
            ensure_running(store)
            if args.action == 'ui':
                value = json.loads((store.directory / 'runtime.json').read_text('utf-8'))
                webbrowser.open(f"http://127.0.0.1:{value['port']}/#token={value['token']}")
            else: print('Connector started.')
        elif args.action == 'disconnect':
            ensure_running(store); control(store, 'disconnect', {}); print('Disconnected and revoked in Vespera.')
        elif args.action in ('configure', 'setup'):
            site = args.vespera or input(f"Vespera site [{store.data['vespera_url']}]: ").strip() or store.data['vespera_url']
            local = args.local_url or input(f"CLIProxy address [{store.data['local_url']}]: ").strip() or store.data['local_url']
            key = getpass.getpass('CLIProxy client API key (Enter keeps existing; type - to clear): ')
            values = {'vespera_url': site, 'local_url': local}
            if key: values['api_key'] = '' if key == '-' else key
            ensure_running(store)
            control(store, 'configure', values)
            if args.action == 'configure':
                print('Configuration saved.'); return
            pairing = control(store, 'setup', {})
            print(f"Open {pairing['verification_uri']} and enter {pairing['user_code']}\nWaiting for your approval. This code expires in 10 minutes.")
            if not args.no_browser: webbrowser.open(pairing['verification_uri_complete'])
            while True:
                state = control(store, 'status')
                if state['paired']:
                    print('Connected. Choose and test a model in Vespera Settings → Models & providers.'); break
                if not state.get('pairing'):
                    raise ValueError(state.get('error') or 'Pairing ended.')
                time.sleep(1)
        if session_thread:
            session_thread.join()
    except KeyboardInterrupt:
        print('\nSetup cancelled. The background connector can be stopped with vespera-connector stop.')
    except Exception as exc:
        # Do not print HTTP request details, which may include device codes or credentials.
        message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else 'Operation failed. Check connectivity and unlock your OS credential store.'
        print(message, file=sys.stderr)
        raise SystemExit(1)
