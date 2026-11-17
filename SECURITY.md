# Security and data flow

1. Your connector makes outbound HTTPS requests to the Vespera site you configure.
2. Device pairing issues a ten-minute, single-use code. Only the initiating connector holds the separate device secret.
3. After you sign in and approve, that connector receives a provider-scoped credential. It is not a Developer API key.
4. Vespera queues model requests for that provider. The connector polls, sends requests to your loopback CLIProxy,
   and returns results to Vespera. The relay handles prompts, model responses, and image references/results.
5. The CLIProxy client key is attached only to local requests. It is never included in requests to Vespera.

Vespera receives the prompts and responses it relays. This is not end-to-end encryption between your browser and CLIProxy.
Your selected CLIProxy may send those requests to its configured upstream provider.

Persistent credentials are in the OS vault. Nonsecret preferences are in your user configuration directory.
Session mode keeps credentials only in memory. No credentials, prompts, or responses are logged by the connector.
The local UI server binds only to `127.0.0.1`, requires a random bearer for API access, rejects foreign
origins and Host headers, and does not enable CORS. Its bootstrap bearer is in a URL fragment and retained
only in that browser tab's session storage. The UI never returns saved credentials.

Only loopback `/v1` provider addresses and an allowlist of operations are accepted. No arbitrary command execution,
remote shell, inbound internet listener, or subscription account administration is provided.

Lost generation responses are uncertain. The connector reconnects, but does not replay the dispatched request.
Check CLIProxy activity before manually retrying a generation.

You can revoke an individual computer from Vespera Settings > Models & providers, even when it is offline.
Revocation stops new claims and receipts; already running provider calls may finish.

Public source is available for inspection and self-building. Check the release tag, build instructions, executable
checksums, and published validation limitations. Current local candidates are unsigned.

Please report suspected vulnerabilities through GitHub's private vulnerability reporting when enabled.
Do not put tokens, prompts, account data, or proxy credentials in public issues.
