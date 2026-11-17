# VesperaSDK contributor instructions

This repository contains only the public connector and Developer API documentation.
Never copy Vespera server source, operator settings, account data, signing keys, or private test receipts here.

Keep CLI and UI on one configuration/runtime. Only loopback `/v1` endpoints are supported.
Never request a CLIProxy management key, log credentials/prompts, replay uncertain generation requests,
or weaken explicit account approval. New operations need bounded inputs/outputs and tests.

Use OS secure storage; retain session-only mode for headless systems without a vault.
Build locally on Windows and Linux and report which OS, desktop/keyring, and packaged flows were verified.
Run `python -m unittest discover -s tests`. Never claim signing or bit-for-bit reproducibility without evidence.
Document actual Vespera API capabilities and use the selected channel's filtered OpenAPI schema.
