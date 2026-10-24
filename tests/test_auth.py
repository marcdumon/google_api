"""The kept token: loaded, renewed when expired, and a clear error when it cannot be used."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials

from google_api import auth


def _token(path: Path, expiry: datetime) -> Path:
    """A token file as Google writes it."""
    path.write_text(json.dumps({'token': 'old', 'refresh_token': 'refresh', 'client_id': 'id', 'client_secret': 'secret',
                                'token_uri': 'https://oauth2.googleapis.com/token',
                                'expiry': expiry.astimezone(UTC).replace(tzinfo=None).isoformat() + 'Z'}))
    return path


def test_no_token_file_asks_for_a_login(tmp_path: Path) -> None:
    with pytest.raises(auth.AuthError, match='Log in'):
        auth.creds(tmp_path / 'token.json')


def test_a_valid_token_is_used_as_it_is(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _token(tmp_path / 'token.json', datetime.now(UTC) + timedelta(hours=1))
    before = path.read_text()
    monkeypatch.setattr(Credentials, 'refresh', lambda self, request: pytest.fail('no renewal of a valid token'))
    assert auth.creds(path).token == 'old'
    assert path.read_text() == before


def test_an_expired_token_is_renewed_and_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _token(tmp_path / 'token.json', datetime.now(UTC) - timedelta(hours=1))

    def renew(self: Credentials, request: object) -> None:
        self.token = 'new'
        self.expiry = (datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None)

    monkeypatch.setattr(Credentials, 'refresh', renew)
    assert auth.creds(path).token == 'new'
    assert json.loads(path.read_text())['token'] == 'new'


def test_a_refused_renewal_says_the_login_expired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _token(tmp_path / 'token.json', datetime.now(UTC) - timedelta(hours=1))

    def refuse(self: Credentials, request: object) -> None:
        raise RefreshError('invalid_grant: Token has been expired or revoked.')

    monkeypatch.setattr(Credentials, 'refresh', refuse)
    with pytest.raises(auth.AuthError, match='Google login expired'):
        auth.creds(path)
