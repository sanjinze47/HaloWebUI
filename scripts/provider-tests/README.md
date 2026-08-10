# Local Provider Tests

These PowerShell scripts store provider API keys outside the repository and encrypt them with Windows DPAPI for the current Windows user and machine.

## Initialize

```powershell
powershell -NoProfile -File .\scripts\provider-tests\provider-secret.ps1 init
```

The local store is created under `%LOCALAPPDATA%\HaloWebUI\provider-tests`.

## Add or update a provider

```powershell
powershell -NoProfile -File .\scripts\provider-tests\provider-secret.ps1 set -Provider sub2api
```

The script prompts for the endpoint, compatibility mode, and API key. The API key is entered as a secure string and is never stored in this repository. After saving, the script calls the provider's `/models` endpoint and prints the discovered model IDs without selecting or persisting a default model.

## List configured providers

```powershell
powershell -NoProfile -File .\scripts\provider-tests\provider-secret.ps1 list
```

This command reports whether an encrypted key exists but never decrypts or prints it.

## Run a local smoke test

```powershell
powershell -NoProfile -File .\scripts\provider-tests\provider-smoke-test.ps1 -Provider sub2api -Scenario responses-stream
```

Supported scenarios are `models`, `chat`, `chat-stream`, `responses`, and `responses-stream`. Test output is limited to status and protocol metadata; response bodies and authorization headers are not printed.

Chat and Responses scenarios require a model selected at invocation time:

```powershell
powershell -NoProfile -File .\scripts\provider-tests\provider-smoke-test.ps1 -Provider sub2api -Scenario responses-stream -Model gpt-5.6-sol
```

## Remove a provider

```powershell
powershell -NoProfile -File .\scripts\provider-tests\provider-secret.ps1 remove -Provider sub2api
```

DPAPI files cannot be moved to another computer or Windows account. Re-enter the provider keys after moving the workspace or changing accounts.
