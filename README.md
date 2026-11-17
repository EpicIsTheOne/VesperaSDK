# VesperaSDK

Open-source connector and Developer API documentation for [Vespera](https://vespera.ephixd.com/).

**Preview:** the new pairing flow requires the matching Vespera server update. Publishing this source
does not mean the connector endpoints have been deployed to Stable or Beta.

The connector connects an **existing CLIProxy installation** to your Vespera account.
It does not install CLIProxy, sign into subscription providers, or require its management key.
Windows and Linux use the same engine, preferences, CLI, and local browser UI.

## Connect

Download the executable for your OS from this repository's releases when a verified release is available.
Packaged executables include Python and dependencies. Building from source requires Python 3.11 or later.
Keep the executable in a permanent location if you enable startup at sign-in.

```console
vespera-connector setup
```

Confirm the Vespera address and your loopback CLIProxy `/v1` address. The default is
`http://127.0.0.1:8317/v1`. Enter a **CLIProxy client API key** only if that endpoint requires one.
Leave it blank to retain the saved key, or enter `-` to clear it. Never enter your management key.

The connector opens Vespera in your browser. Sign in and explicitly approve the computer.
For a headless computer, use `setup --no-browser`: open the printed simple link on any device,
enter the displayed code, and approve. Codes expire after ten minutes.

For the graphical settings window:

```console
vespera-connector ui
```

Double-clicking the executable also opens settings. The UI is a local browser page, not a second account login.
Closing that window leaves the connector running. Choose and test your models in
Vespera Settings > Models & providers. Discovering models never runs a paid generation or changes assignments.

```console
vespera-connector status
vespera-connector configure
vespera-connector start
vespera-connector stop
vespera-connector run
vespera-connector disconnect
vespera-connector autostart enable
vespera-connector autostart disable
```

`run` stays in the foreground. `disconnect` revokes the account credential, while keeping the provider's saved model settings.
Removing the provider in Vespera also revokes access. Already dispatched local calls may finish after revocation.
Startup uses the current Windows user's Run key or a Linux systemd user unit, with no administrator access.
Enabling it is optional; a fresh sign-in is needed to verify it on your system.

Select Beta explicitly with `setup --vespera https://vespera.ephixd.com/beta/`.
Pairing and relay traffic stay on the selected site's channel.

## Headless Linux and credential storage

Persistent credentials use Windows Credential Manager or Linux Secret Service/KWallet.
On Linux, install and unlock a supported keyring and run in that user's D-Bus session.
The connector refuses plaintext keyring backends.

For a headless host without a keyring:

```console
vespera-connector setup --session --no-browser
```

This keeps both credentials **only in memory** and stays in the foreground, suitable for a terminal multiplexer.
Keep it running while Vespera uses the provider. Stopping it loses the credential, so revoke the old connection
in Vespera and pair again next time. Session mode does not support unattended persistent autostart.

## Inspect and build

```console
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux: source .venv/bin/activate
python -m pip install -e . pyinstaller==6.16.0
python -m unittest discover -s tests
python build.py
python check_candidate.py
```

Build on each target OS; PyInstaller does not cross-compile Windows/Linux executables.
`dist/<platform>/SHA256SUMS` records the exact executable hash. Local candidates are unsigned until an explicitly signed release is produced.
A hash detects changed bytes; it is not a digital signature or proof that a binary matches its source.
`SOURCE.json` records the executable hash and hashes of the runtime/build inputs. The candidate check refuses
stale source or changed executable bytes before exercising the packaged UI and credential paths.

See [security and data flow](SECURITY.md), [protocol](docs/connector-protocol.md), and [Developer API](docs/developer-api.md).
Dependency licenses are summarized in [third-party components](THIRD_PARTY.md).

## Source map

* `vespera_connector/config.py`: URL validation, preferences, OS credentials, session vault.
* `vespera_connector/relay.py`: bounded models, completion, and image requests.
* `vespera_connector/runtime.py`: one background process, device pairing, authenticated loopback UI server.
* `vespera_connector/cli.py`: CLI, browser launch, process control, optional sign-in startup.
* `vespera_connector/ui.html`: self-contained graphical settings, with no external scripts.

The Vespera application server and private operator configuration are not part of this repository.
