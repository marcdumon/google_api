# google_api

Google APIs for my own apps. The library keeps nothing: each app keeps its Google OAuth client file and its tokens in its
own `secrets/` folder (not in git), and decides where the data goes. The functions give back plain Python values
(dicts, lists, text and bytes).

## Parts

| Module | What it does |
|---|---|
| `auth` | `login(client_file, token_file, scopes)`: the browser login, once; the token is kept readable by the user only. `creds(token_file, scopes=None)`: the kept token, renewed and saved again when it expires, never with a browser. `status(token_file, scopes)`: whether the token can be used, and why not. `service(name, version, creds)`: a Google API client. `AuthError` when there is no token or the login expired. |
| `calendar` | `writable_calendars`, `timezone`, `events_tagged` (by a private property), `events_between` (repeating events as single occurrences) and `all_events`, every page of a list. |
| `gmail` | `labels`, `message_ids` (a search with a limit, and whether there were more), `metadata` (sender, recipients, subject, preview, labels), `body_text`, `mail_pdfs`, and `sender`, `received` and `gmail_link` for a list of mails. |
| `health` | The Google Health API (Fitbit data). `collect(creds, folder, first, last, tz)` saves every data type of every local day as the API sends it, one file per type and day in `<folder>/<type>/<YYYY-MM-DD>.json`. A day is fetched again until two days after it ended. `rows(folder, day=None)` reads the files back as rows (`COLUMNS`), a row per value, without duplicates; with a day, only the files of that local day. `SCOPES` are the read scopes of a Health login. |

## Use in an app

Link the library folder, so that a change here is live in the app at once:

```bash
uv add --editable ../google_api
```

```python
from google_api import auth, calendar, health

svc = auth.service('calendar', 'v3', auth.creds(SECRETS / 'token.json'))
events = calendar.events_between(svc, 'primary', '2026-10-24T00:00:00Z', None)

counts = health.collect(auth.creds(SECRETS / 'google_health_token.json'), RAW / 'google_health', first, last, tz)
rows = health.rows(RAW / 'google_health')
```

## Tests

```bash
uv run pytest      # no network: a fake API answers
```
