"""The Google login of an app: its token file is kept by the app (in its own secrets folder) and renewed here when it
expires. Nothing here opens a browser."""

from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


class AuthError(RuntimeError):
    """No usable Google token; the user has to log in (again)."""


def creds(token_file: Path, scopes: list[str] | None = None) -> Credentials:
    """The token of `token_file`, renewed and saved again when expired. Without `scopes`, the scopes of the file."""
    if not token_file.exists():
        raise AuthError(f'No Google token at {token_file}. Log in first.')
    c = Credentials.from_authorized_user_file(str(token_file), scopes)
    if not c.valid:
        try:
            c.refresh(Request())
        except RefreshError as error:
            # Testing-mode consent screens expire refresh tokens after about a week
            raise AuthError(f'Google login expired: {error}') from error
        token_file.write_text(c.to_json())
    return c
