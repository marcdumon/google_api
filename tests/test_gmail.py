"""The Gmail helpers: the search with its limit, the headers of a mail, its text and its PDF attachments."""

import base64
from zoneinfo import ZoneInfo

from conftest import FakeGoogle, pages

from google_api import gmail


def _data(text: str | bytes) -> str:
    """A body part as Gmail sends it: base64url without padding."""
    raw = text.encode() if isinstance(text, str) else text
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def test_the_labels_are_all_labels() -> None:
    svc = FakeGoogle({'users.labels.list': lambda userId: {'labels': [{'id': 'INBOX'}]}})
    assert gmail.labels(svc) == [{'id': 'INBOX'}]


def test_the_search_stops_at_the_limit_and_says_there_were_more() -> None:
    svc = FakeGoogle({'users.messages.list': pages([{'id': 'm1'}, {'id': 'm2'}], [{'id': 'm3'}], key='messages')})
    assert gmail.message_ids(svc, 'from:bank', ['INBOX'], 2) == ([{'id': 'm1'}, {'id': 'm2'}], True)
    asked = svc.calls[0][1]
    assert (asked['q'], asked['labelIds'], asked['maxResults']) == ('from:bank', ['INBOX'], 2)


def test_the_search_gives_every_page_below_the_limit() -> None:
    svc = FakeGoogle({'users.messages.list': pages([{'id': 'm1'}], [{'id': 'm2'}], key='messages')})
    assert gmail.message_ids(svc, '', [], 10) == ([{'id': 'm1'}, {'id': 'm2'}], False)
    assert (svc.calls[0][1]['q'], svc.calls[0][1]['labelIds']) == (None, None)


def test_the_metadata_of_a_mail_has_its_headers_and_a_clean_preview() -> None:
    raw = {'id': 'm1', 'threadId': 't1', 'labelIds': ['INBOX'], 'snippet': 'Hello&nbsp;​  there &amp; more',
           'internalDate': '1790000000000',
           'payload': {'headers': [{'name': 'From', 'value': 'Bank <info@bank.be>'}, {'name': 'Subject', 'value': 'Statement'}]}}
    svc = FakeGoogle({'users.messages.get': lambda **kwargs: raw})
    meta = gmail.metadata(svc, 'm1')
    assert meta == {'id': 'm1', 'thread_id': 't1', 'labels': ['INBOX'], 'from': 'Bank <info@bank.be>', 'to': '',
                    'subject': 'Statement', 'snippet': 'Hello there & more', 'received_ms': 1790000000000}
    assert svc.calls[0][1]['format'] == 'metadata'


def test_the_body_text_is_the_plain_part_when_there_is_one() -> None:
    raw = {'payload': {'mimeType': 'multipart/alternative', 'parts': [
        {'mimeType': 'text/plain', 'body': {'data': _data('Plain text')}},
        {'mimeType': 'text/html', 'body': {'data': _data('<p>Markup</p>')}}]}}
    svc = FakeGoogle({'users.messages.get': lambda **kwargs: raw})
    assert gmail.body_text(svc, 'm1') == 'Plain text'


def test_the_body_text_of_an_html_mail_has_no_markup_scripts_or_entities() -> None:
    markup = '<style>p {color: red}</style><p>One &amp; two</p><br>Three<script>alert(1)</script>'
    svc = FakeGoogle({'users.messages.get': lambda **kwargs: {'payload': {'mimeType': 'text/html', 'body': {'data': _data(markup)}}}})
    text = gmail.body_text(svc, 'm1')
    assert text.split() == ['One', '&', 'two', 'Three']


def test_the_pdfs_of_a_mail_come_inline_or_as_a_fetched_attachment() -> None:
    raw = {'payload': {'parts': [
        {'filename': 'a.pdf', 'mimeType': 'application/pdf', 'body': {'data': _data(b'%PDF-a')}},
        {'filename': 'b.PDF', 'mimeType': 'application/octet-stream', 'body': {'attachmentId': 'att1'}},
        {'filename': 'c.txt', 'mimeType': 'text/plain', 'body': {'data': _data('no')}}]}}
    svc = FakeGoogle({'users.messages.get': lambda **kwargs: raw,
                      'users.messages.attachments.get': lambda userId, messageId, id: {'data': _data(b'%PDF-b')}})
    assert gmail.mail_pdfs(svc, 'm1') == [('a.pdf', b'%PDF-a'), ('b.PDF', b'%PDF-b')]


def test_the_sender_is_the_name_or_the_address() -> None:
    assert gmail.sender({'from': 'Bank <info@bank.be>'}) == 'Bank'
    assert gmail.sender({'from': 'info@bank.be'}) == 'info@bank.be'
    assert gmail.sender({'from': ''}) == '—'


def test_the_time_a_mail_arrived_and_its_link() -> None:
    assert gmail.received({'received_ms': 1790000000000}, ZoneInfo('Europe/Brussels')) == '21 Sep 2026 16:13'
    assert gmail.received({'received_ms': 0}, ZoneInfo('Europe/Brussels')) == '—'
    assert gmail.gmail_link('t1') == 'https://mail.google.com/mail/u/0/#all/t1'
