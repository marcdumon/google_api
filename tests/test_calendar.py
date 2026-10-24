"""The Calendar helpers: every page of a list, and the right question to the API."""

from conftest import FakeGoogle, pages

from google_api import calendar


def test_the_writable_calendars_come_from_every_page() -> None:
    svc = FakeGoogle({'calendarList.list': pages([{'id': 'a'}], [{'id': 'b'}])})
    assert [c['id'] for c in calendar.writable_calendars(svc)] == ['a', 'b']
    assert [kwargs['minAccessRole'] for _, kwargs in svc.calls] == ['writer', 'writer']
    assert [kwargs['pageToken'] for _, kwargs in svc.calls] == [None, 'p1']


def test_the_timezone_is_the_calendar_setting() -> None:
    svc = FakeGoogle({'settings.get': lambda setting: {'value': 'Europe/Brussels'} if setting == 'timezone' else {}})
    assert calendar.timezone(svc) == 'Europe/Brussels'


def test_tagged_events_are_found_by_their_private_property() -> None:
    svc = FakeGoogle({'events.list': pages([{'id': 'e1'}], [{'id': 'e2'}])})
    assert [e['id'] for e in calendar.events_tagged(svc, 'cal', 'source', 'site')] == ['e1', 'e2']
    assert svc.calls[0][1]['privateExtendedProperty'] == 'source=site'
    assert svc.calls[0][1]['calendarId'] == 'cal'


def test_events_between_two_times_come_as_single_occurrences_in_time_order() -> None:
    svc = FakeGoogle({'events.list': pages([{'id': 'e1'}])})
    assert calendar.events_between(svc, 'cal', '2026-10-24T00:00:00Z', None) == [{'id': 'e1'}]
    asked = svc.calls[0][1]
    assert (asked['timeMin'], asked['timeMax'], asked['singleEvents'], asked['orderBy']) == ('2026-10-24T00:00:00Z', None, True,
                                                                                             'startTime')


def test_all_events_of_a_calendar_keep_a_repeating_event_once() -> None:
    svc = FakeGoogle({'events.list': pages([{'id': 'e1'}], [{'id': 'e2'}])})
    assert [e['id'] for e in calendar.all_events(svc, 'cal')] == ['e1', 'e2']
    assert 'singleEvents' not in svc.calls[0][1]
