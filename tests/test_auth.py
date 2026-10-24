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


SCOPES = ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/gmail.modify']


class Flow:
    """A fake browser login that grants some scopes."""

    def __init__(self, granted: list[str]) -> None:
        self.granted = granted

    def run_local_server(self, port: int, open_browser: bool) -> Credentials:
        """The token of the login."""
        found = Credentials(token='new', refresh_token='refresh', client_id='id', client_secret='secret',
                            token_uri='https://oauth2.googleapis.com/token', scopes=SCOPES)
        found._granted_scopes = self.granted
        return found


def test_a_login_without_a_client_file_says_where_it_goes(tmp_path: Path) -> None:
    with pytest.raises(auth.AuthError, match=r'client_secret\.json'):
        auth.login(tmp_path / 'client_secret.json', tmp_path / 'token.json', SCOPES)


def test_a_login_keeps_the_token_for_the_user_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = tmp_path / 'client_secret.json'
    client.write_text('{}')
    monkeypatch.setattr(auth.InstalledAppFlow, 'from_client_secrets_file', lambda path, scopes: Flow(SCOPES))
    token = tmp_path / 'secrets' / 'token.json'
    assert auth.login(client, token, SCOPES).token == 'new'
    assert json.loads(token.read_text())['token'] == 'new'
    assert token.stat().st_mode & 0o777 == 0o600


def test_a_login_with_an_unticked_box_names_it_and_keeps_no_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = tmp_path / 'client_secret.json'
    client.write_text('{}')
    monkeypatch.setattr(auth.InstalledAppFlow, 'from_client_secrets_file', lambda path, scopes: Flow(SCOPES[:1]))
    with pytest.raises(auth.AuthError, match=r'Not granted: gmail\.modify'):
        auth.login(client, tmp_path / 'token.json', SCOPES)
    assert not (tmp_path / 'token.json').exists()


def test_the_status_says_whether_the_token_can_be_used(tmp_path: Path) -> None:
    ok, message = auth.status(tmp_path / 'token.json', SCOPES)
    assert not ok
    assert 'Log in' in message
    path = _token(tmp_path / 'token.json', datetime.now(UTC) + timedelta(hours=1))
    assert auth.status(path, SCOPES) == (True, 'Logged in')


def test_a_service_is_built_without_the_network(tmp_path: Path) -> None:
    path = _token(tmp_path / 'token.json', datetime.now(UTC) + timedelta(hours=1))
    svc = auth.service('calendar', 'v3', auth.creds(path))
    assert hasattr(svc, 'events')
