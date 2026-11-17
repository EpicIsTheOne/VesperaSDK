# Vespera Developer API

The Developer API is separate from local connector pairing. Create a personal, scoped key in
**Account > Developer access**. Save it securely; send it as `Authorization: Bearer <key>`.
Never embed it in frontend bundles, public repositories, or URLs.

Base addresses:

* Stable: `https://vespera.ephixd.com/api/v1/`
* Beta: `https://vespera.ephixd.com/beta/api/v1/`

The authoritative machine-readable schema for each deployed channel is `openapi.json` below that base.
It describes the deployed request/response models. Consult it before generating a client; this document
is an introduction, not a guarantee that an unshipped candidate is live.

```python
import getpass
import httpx

key = getpass.getpass('Vespera Developer key: ')
with httpx.Client(base_url='https://vespera.ephixd.com/api/v1/',
                  headers={'Authorization': 'Bearer ' + key}, timeout=30) as client:
    response = client.get('capabilities')
    response.raise_for_status()
    print(response.json())
```

## Supported areas

Access depends on the key's scopes, selected characters, granted conversations, expiry, and account limits.
Existing server routes include:

| Area | Routes relative to `/api/v1/` |
| --- | --- |
| Capabilities and models | `GET capabilities`, `GET models` |
| Characters | `GET characters`, `GET characters/{id}`, `GET characters/{id}/export` |
| Conversations | `GET/POST conversations`, `GET conversations/{id}` |
| Messages | `POST conversations/{id}/messages` returns an asynchronous operation |
| Operations | `GET operations/{id}`, `GET operations/{id}/events`, `POST operations/{id}/cancel` |
| Agent jobs | `GET agents/{character_id}`, `GET/POST agents/{character_id}/jobs`, `GET jobs/{id}` |
| Memory | `GET conversations/{id}/memories`, scoped patch/delete of individual memories |
| Images | `POST conversations/{id}/images`, `GET conversations/{id}/images/{image_id}` |
| Usage | `GET usage` |

Further branch/export, voice, job scheduling, events, and compatibility details are in the filtered OpenAPI schema.
Generation endpoints can consume provider credits and normal Vespera allowances. Read-only discovery does not
authorize generation, and connector pairing does not grant Developer API scopes.

Handle `401` for invalid/expired/revoked credentials, `403` for insufficient access, and `429` for limits.
For asynchronous messages, follow the returned operation rather than resubmitting blindly after a timeout.
Do not assume cancellation can undo a provider call already in progress.
