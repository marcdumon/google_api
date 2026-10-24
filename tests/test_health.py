"""The Google Health collector and reader: day ranges, when a day is fetched again, the saved files, and the points as rows."""

import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from google_api import health

TZ = ZoneInfo('Europe/Brussels')
HR_POINT = {'dataSource': {'recordingMethod': 'PASSIVELY_MEASURED', 'device': {'displayName': 'Fitbit Air'}, 'platform': 'FITBIT'},
            'heartRate': {'sampleTime': {'physicalTime': '2026-10-23T13:32:55Z', 'utcOffset': '7200s'}, 'beatsPerMinute': '71'}}
STEPS_POINT = {'dataSource': {'recordingMethod': 'PASSIVELY_MEASURED', 'device': {'displayName': 'MobileTrack'}},
               'steps': {'interval': {'startTime': '2026-10-23T13:32:00Z', 'endTime': '2026-10-23T13:33:00Z'}, 'count': '16'}}
ZONES_POINT = {'dataSource': {'recordingMethod': 'DERIVED', 'platform': 'FITBIT'},
               'dailyHeartRateZones': {'date': {'year': 2026, 'month': 10, 'day': 23},
                                       'heartRateZones': [{'heartRateZoneType': 'LIGHT', 'minBeatsPerMinute': '30'},
                                                          {'heartRateZoneType': 'PEAK', 'minBeatsPerMinute': '166'}]}}
LEVEL_POINT = {'dataSource': {'recordingMethod': 'DERIVED', 'device': {'displayName': 'Fitbit Air'}, 'platform': 'FITBIT'},
               'activityLevel': {'interval': {'startTime': '2026-10-23T13:32:00Z', 'endTime': '2026-10-23T13:33:00Z'},
                                 'activityLevelType': 'LIGHTLY_ACTIVE'}}
ROLLUP_POINT = {'startTime': '2026-10-23T12:35:00Z', 'endTime': '2026-10-23T12:36:00Z', 'totalCalories': {'kcalSum': 1.5}}


class Answer:
    """A fake answer of the API."""

    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code, self.body = status_code, body

    def raise_for_status(self) -> None:
        """Fail on an error status, as requests does."""
        if self.status_code >= 400:
            raise RuntimeError(f'{self.status_code} Error')

    def json(self) -> dict:
        """The body."""
        return self.body


class FakeApi:
    """A fake Google Health API: every type answers with an empty page unless an answer is set for it."""

    def __init__(self, answers: dict[str, list[Answer]] | None = None) -> None:
        self.answers = answers or {}
        self.asked: list[str] = []

    def _answer(self, url: str, empty: dict) -> Answer:
        kind = url.split('/dataTypes/')[1].split('/')[0]
        self.asked.append(kind)
        waiting = self.answers.get(kind)
        return waiting.pop(0) if waiting else Answer(200, empty)

    def get(self, url: str, params: dict) -> Answer:
        """A list request."""
        return self._answer(url, {'dataPoints': []})

    def post(self, url: str, json: dict) -> Answer:
        """A roll-up request."""
        return self._answer(url, {'rollupDataPoints': []})


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> FakeApi:
    """The fake API in place of the real one, with no waits between tries."""
    fake = FakeApi()
    monkeypatch.setattr(health, 'AuthorizedSession', lambda creds: fake)
    monkeypatch.setattr(health, 'RETRY_WAITS_S', (0, 0))
    return fake


def test_a_day_runs_from_local_midnight_to_local_midnight() -> None:
    start, end = health.day_range(date(2026, 10, 23), TZ)
    assert (start, end) == (datetime(2026, 10, 22, 22, tzinfo=UTC), datetime(2026, 10, 23, 22, tzinfo=UTC))


def test_the_day_the_clock_goes_back_has_25_hours() -> None:
    start, end = health.day_range(date(2026, 10, 25), TZ)
    assert (end - start).total_seconds() == 25 * 3600


def test_a_day_is_fetched_until_two_days_after_it_ended(tmp_path: Path) -> None:
    path = tmp_path / '2026-10-23.json'
    day = date(2026, 10, 23)
    assert health.needs_fetch(path, day, TZ)
    path.write_text(json.dumps({'fetched_at': '2026-10-24T08:00:00+00:00'}))
    assert health.needs_fetch(path, day, TZ)
    path.write_text(json.dumps({'fetched_at': '2026-10-25T23:00:00+00:00'}))
    assert not health.needs_fetch(path, day, TZ)


def test_each_type_of_each_day_gets_a_file_and_a_settled_day_is_not_fetched_again(tmp_path: Path, api: FakeApi) -> None:
    settled = tmp_path / 'heart-rate' / '2026-10-20.json'
    settled.parent.mkdir()
    settled.write_text(json.dumps({'fetched_at': '2026-10-23T00:00:00+00:00', 'pages': []}))
    counts = health.collect(None, tmp_path, date(2026, 10, 20), date(2026, 10, 21), TZ)
    by_day = len(health.TYPES) - 1
    assert counts == {'written': 2 * by_day + 1 - 1, 'failed': 0}
    assert (tmp_path / 'exercise' / 'all.json').is_file()
    assert (tmp_path / 'total-calories' / '2026-10-21.json').is_file()
    assert json.loads(settled.read_text())['fetched_at'] == '2026-10-23T00:00:00+00:00'
    saved = json.loads((tmp_path / 'heart-rate' / '2026-10-21.json').read_text())
    assert (saved['type'], saved['day'], saved['pages']) == ('heart-rate', '2026-10-21', [{'dataPoints': []}])
    assert not list(tmp_path.glob('*/*.part'))


def test_a_failing_type_does_not_stop_the_others(tmp_path: Path, api: FakeApi, caplog: pytest.LogCaptureFixture) -> None:
    api.answers['weight'] = [Answer(403, {})]
    with caplog.at_level(logging.WARNING):
        counts = health.collect(None, tmp_path, date(2026, 10, 21), date(2026, 10, 21), TZ)
    assert counts == {'written': len(health.TYPES) - 1, 'failed': 1}
    assert not (tmp_path / 'weight').exists()
    assert 'weight 2026-10-21: 403 Error' in caplog.text


def test_every_page_of_an_answer_is_kept_and_a_busy_api_is_asked_again(tmp_path: Path, api: FakeApi) -> None:
    api.answers['steps'] = [Answer(503, {}), Answer(200, {'dataPoints': [STEPS_POINT], 'nextPageToken': 'p2'}),
                            Answer(200, {'dataPoints': [STEPS_POINT]})]
    health.collect(None, tmp_path, date(2026, 10, 23), date(2026, 10, 23), TZ)
    assert api.asked.count('steps') == 3
    assert len(json.loads((tmp_path / 'steps' / '2026-10-23.json').read_text())['pages']) == 2


def test_points_become_rows_with_their_time_value_and_device() -> None:
    rows = health.point_rows('heart-rate', [HR_POINT])
    assert rows == [{'type': 'heart-rate', 'start': '2026-10-23T13:32:55Z', 'end': '2026-10-23T13:32:55Z', 'date': None,
                     'field': 'beatsPerMinute', 'value': 71.0, 'text': None, 'device': 'Fitbit Air', 'method': 'PASSIVELY_MEASURED'}]


def test_interval_daily_and_rollup_points_keep_their_own_times() -> None:
    steps = health.point_rows('steps', [STEPS_POINT])[0]
    assert (steps['start'], steps['end'], steps['value'], steps['device']) == ('2026-10-23T13:32:00Z', '2026-10-23T13:33:00Z', 16.0,
                                                                              'MobileTrack')
    zones = health.point_rows('daily-heart-rate-zones', [ZONES_POINT])
    assert [(z['date'], z['field'], z['value']) for z in zones] == [('2026-10-23', 'heartRateZones[LIGHT].minBeatsPerMinute', 30.0),
                                                                   ('2026-10-23', 'heartRateZones[PEAK].minBeatsPerMinute', 166.0)]
    level = health.point_rows('activity-level', [LEVEL_POINT])[0]
    assert (level['field'], level['value'], level['text']) == ('activityLevelType', None, 'LIGHTLY_ACTIVE')
    total = health.point_rows('total-calories', [ROLLUP_POINT])[0]
    assert (total['start'], total['field'], total['value'], total['device']) == ('2026-10-23T12:35:00Z', 'kcalSum', 1.5, None)


def test_the_parts_of_a_point_keep_their_own_times() -> None:
    sleep = {'dataSource': {'recordingMethod': 'DERIVED', 'device': {'displayName': 'Fitbit Air'}},
             'sleep': {'interval': {'startTime': '2026-10-23T23:01:00Z', 'endTime': '2026-10-24T08:31:00Z'},
                       'stages': [{'startTime': '2026-10-23T23:01:00Z', 'endTime': '2026-10-23T23:05:00Z', 'type': 'AWAKE'}]}}
    rows = health.point_rows('sleep', [sleep])
    assert {(r['field'], r['text']) for r in rows} == {('stages[0].startTime', '2026-10-23T23:01:00Z'),
                                                      ('stages[0].endTime', '2026-10-23T23:05:00Z'), ('stages[0].type', 'AWAKE')}
    assert {(r['start'], r['end']) for r in rows} == {('2026-10-23T23:01:00Z', '2026-10-24T08:31:00Z')}


def test_the_saved_files_become_rows_without_duplicates(tmp_path: Path) -> None:
    for day in ('2026-10-23', '2026-10-24'):
        (tmp_path / 'heart-rate').mkdir(exist_ok=True)
        (tmp_path / 'heart-rate' / f'{day}.json').write_text(json.dumps({'pages': [{'dataPoints': [HR_POINT]}]}))
    (tmp_path / 'total-calories').mkdir()
    (tmp_path / 'total-calories' / '2026-10-23.json').write_text(json.dumps({'pages': [{'rollupDataPoints': [ROLLUP_POINT]}]}))
    rows = health.rows(tmp_path)
    assert [(r['type'], r['start'], r['field']) for r in rows] == [('heart-rate', '2026-10-23T13:32:55Z', 'beatsPerMinute'),
                                                                   ('total-calories', '2026-10-23T12:35:00Z', 'kcalSum')]
    assert list(rows[0]) == list(health.COLUMNS)
