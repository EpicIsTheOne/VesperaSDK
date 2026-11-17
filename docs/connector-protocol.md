# Connector protocol v1

All server paths below are relative to the configured Vespera site, including `/beta/` when selected.

## Device pairing

* `POST api/provider-bridges/device/start` with `{ "name": "My computer" }` returns `device_code`,
  `user_code`, `verification_uri`, `verification_uri_complete`, `expires_in`, and `interval`.
* The user opens `verification_uri`, signs in, enters `user_code`, inspects the requesting name,
  and explicitly approves or denies. A prefilled link does not auto-approve.
* Poll `POST api/provider-bridges/device/token` with `{ "device_code": "..." }` no faster than `interval` seconds.
  Responses use `status`: `authorization_pending`, `slow_down`, `access_denied`, `expired_token`, or `connected`.
* A connected response contains `provider_id` and `token`, returned once. Save the token securely.
  A lost exchange response requires a new pairing; remove the unused provider from settings.

Browser-only account endpoints: `GET device/inspect?code=...`, `POST device/approve`
with `{ "user_code": "ABCD-EFGH", "approve": true }`, `GET devices`, and `DELETE devices/{provider_id}`,
all under `api/provider-bridges/`. Normal authenticated-write Origin checks apply.

## Relay

Use `Authorization: Bearer <connector-token>` with `GET api/provider-bridges/poll`.
An idle response is `{ "id": null }`. A claim contains an `id` and a `request` with an allowlisted
`operation` and `payload`. Operations are `models`, `completion`, `image_generation`, and `image_edit`.
Submit one receipt with `POST api/provider-bridges/requests/{id}` and `{ "result": { ... } }`.
Neither a dispatched provider request nor an uncertain receipt is automatically replayed.
Text/model results are bounded to 500 KB; image results to 16 MB.

`DELETE api/provider-bridges/device/session` with the connector bearer revokes its own access.
The token cannot read account chats, manage subscription accounts, or call the Developer API.

## Local UI API

The executable opens a random loopback port. CLI commands and UI use that process, not separate credentials.
All `/api/*` endpoints require the random local bearer. `GET /api/status` exposes only nonsecret status.
`POST /api/configure`, `/api/setup`, `/api/check`, `/api/disconnect`, and `/api/shutdown` perform explicit operations.
The local UI bearer is not the Vespera connector bearer or the CLIProxy key.
