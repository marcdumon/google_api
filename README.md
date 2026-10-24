# google_api

Google APIs for my own apps. The library keeps nothing: each app keeps its Google OAuth client file and its tokens in its
own `secrets/` folder (not in git), and decides where the data goes.

## Parts

| Module | What it does |
|---|---|
| `auth` | `creds(token_file, scopes=None)`: the kept token, renewed and saved again when it expires. Never opens a browser. `AuthError` when there is no token or the login expired. |
| `health` | The Google Health API (Fitbit data). `collect(creds, folder, first, last, tz)` saves every data type of every local day as the API sends it, one file per type and day in `<folder>/<type>/<YYYY-MM-DD>.json`. A day is fetched again until two days after it ended. `rows(folder)` reads the files back as rows (`COLUMNS`), a row per value, without duplicates. `SCOPES` are the read scopes of a Health login. |

## Use in an app

Link the library folder, so that a change here is live in the app at once:

```bash
uv add --editable ../google_api
```

```python
from google_api import auth, health

counts = health.collect(auth.creds(SECRETS / 'google_health_token.json'), RAW / 'google_health', first, last, tz)
rows = health.rows(RAW / 'google_health')
```

## Tests

```bash
uv run pytest      # no network: a fake API answers
```
