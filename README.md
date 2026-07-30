## Konecty Python SDK

> 🛠️ Work in progress

This project exposes both:

- a cli for interacting with the database
- the Konecty client sdk for interacting with Konecty's api

#### Usage

##### Installing on a project

```sh
uv pip install konecty-sdk-python
konecty-cli apply --mongo-url="..." --database my-db
```

##### Running on uvx

```sh
uvx --from konecty-sdk-python konecty-cli pull --all --mongo-url="..." --database my-db
```

#### Google login

The Konecty core hosts the whole authorization code flow: your app never talks to Google
and never sees `client_secret`. The `authId` never travels in a URL — the callback returns
a single-use code (TTL 60s) and the `authId` only exists in the body of `POST /api/auth/google/session`.

Three steps, three methods:

1. `client.google_login_url(...)` — build the URL to send the browser to (no request is made).
2. the browser comes back to your `redirect_uri` with `?code=...&state=...` (or `?error=...&state=...`).
3. `await client.exchange_google_code(code)` — turn the code into a session; the returned
   `authId` is adopted by the client, so the next calls are authenticated.

```python
import asyncio
import os
import secrets

from KonectySdkPython import KonectyClient
from KonectySdkPython.lib.exceptions import KonectyAPIError

KONECTY_URL = os.environ["KONECTY_URL"]
CLIENT_ID = os.environ["KONECTY_CLIENT_ID"]
REDIRECT_URI = os.environ["KONECTY_REDIRECT_URI"]


async def main() -> None:
    client = KonectyClient(KONECTY_URL)

    # Is Google login enabled for this namespace?
    options = await client.get_login_options()
    if not options["googleEnabled"]:
        raise SystemExit("Google login is disabled for this namespace")

    # Step 1 — send the browser here (state is opaque to Konecty; use it against CSRF).
    state = secrets.token_urlsafe(16)
    print(client.google_login_url(client_id=CLIENT_ID, redirect_uri=REDIRECT_URI, state=state))

    # Step 2 — Konecty redirects the browser back to REDIRECT_URI with code + state.
    #          On refusal it comes back as ?error=<access_denied|provider_error|
    #          email_not_verified|user_not_found|user_inactive|ambiguous_user>&state=...
    returned_code = input("code from the callback: ")

    # Step 3 — exchange the single-use code for a session.
    try:
        session = await client.exchange_google_code(
            returned_code,
            source="my-app",  # optional telemetry: geolocation, resolution, source, fingerprint
        )
    except KonectyAPIError as error:
        raise SystemExit(f"Google login failed: {error}")

    print("logged as", session["user"]["login"], "authId:", client.auth_id)

    # The client is now authenticated: no token needed on the constructor.
    contacts = await client.find_by_id("User", session["user"]["_id"])
    print(contacts)


asyncio.run(main())
```

`exchange_google_code` raises `KonectyAPIError` with the message of `errors[0]`
(`invalid_code`, `expired_code`, `user_not_found`, `user_inactive`) and leaves the client's
authentication state untouched.

#### Tests

```sh
uv pip install -e ".[dev]"
.venv/bin/python -m pytest
```

#### Build & Publish

Publishing runs from the **Publish** workflow, triggered by hand from the Actions tab
(`Run workflow`) — no merge publishes on its own. Pick the increment (`patch`, `minor` or
`major`) and run it; **the version bump is part of publishing**, so there is nothing to edit
beforehand.

The workflow runs the tests, bumps `version` in [pyproject.toml](./pyproject.toml), builds into
`dist-build/` and uploads with `uv publish` (secret `PYPI_API_TOKEN`). Only after the upload
succeeds does it commit `chore(release): <version>` and tag it — a failed upload leaves no bump
behind claiming a release that does not exist on PyPI.

<details>
<summary>Publishing manually</summary>

Same PyPI endpoint (`upload.pypi.org/legacy/`) and the same kind of API token. Credentials
come from `.pypirc`, which is gitignored and therefore local-only — this is why CI
authenticates through a secret instead.

```sh
uv build
uvx twine upload --config-file .pypirc --skip-existing dist/*
```

Note `--skip-existing`: unlike the workflow, this silently skips versions already published,
and it is what keeps a stale local `dist/` from re-uploading old artifacts.

</details>
