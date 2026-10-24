"""The Google login of an app: the app keeps its OAuth client file and its token file (in its own secrets folder); the
browser login happens once here, and the token is renewed when it expires without a browser."""

import os
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build


class AuthError(RuntimeError):
    """No usable Google token; the user has to log in (again)."""


def login(client_file: Path, token_file: Path, scopes: list[str]) -> Credentials:
    """Run the browser consent flow and keep the token in `token_file`, readable by the user only."""
    if not client_file.exists():
        raise AuthError(f'No OAuth client secret at {client_file}. Download it from Google Cloud Console '
                        '(APIs & Services, Credentials, OAuth client of type Desktop) and save it there.')
    # accept a token with fewer scopes, so that the unticked box is named instead of a crash
    os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), scopes)
    c = flow.run_local_server(port=0, open_browser=True)
    missing = [s.rsplit('/', 1)[-1] for s in scopes if s not in set(c.granted_scopes or scopes)]
    if missing:
        raise AuthError(f"Not granted: {', '.join(missing)}. Log in again and tick every box.")
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(c.to_json())
    token_file.chmod(0o600)
    return c


def creds(token_file: Path, scopes: list[str] | None = None) -> Credentials:
    """The token of `token_file`, renewed and saved again when expired. Without `scopes`, the scopes of the file."""
    if not token_file.exists():
        raise AuthError(f'No Google token at {token_file}. Log in first.')
    c = Credentials.from_authorized_user_file(str(token_file), scopes)
    if not c.valid:
        try:
            c.refresh(Request())
        except RefreshError as error:
            raise AuthError(f'Google login expired: {error}') from error
        token_file.write_text(c.to_json())
    return c


def status(token_file: Path, scopes: list[str]) -> tuple[bool, str]:
    """Whether a usable token exists, and why not if it doesn't."""
    try:
        c = creds(token_file, scopes)
    except AuthError as error:
        return False, str(error)
    missing = [s.rsplit('/', 1)[-1] for s in scopes if c.scopes and s not in c.scopes]
    if missing:
        return False, f"Token lacks scope: {', '.join(missing)}. Log in again."
    return True, 'Logged in'


def service(name: str, version: str, c: Credentials) -> Resource:
    """A Google API client, e.g. service('calendar', 'v3', creds(token_file))."""
    return build(name, version, credentials=c, cache_discovery=False)
