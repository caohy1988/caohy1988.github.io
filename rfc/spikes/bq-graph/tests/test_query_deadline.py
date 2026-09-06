"""Real Client/QueryJob/RowIterator, replacing only submission and HTTP transport."""
import json
import threading
import time
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from google.auth.credentials import AnonymousCredentials
from google.cloud import bigquery

from okf_bq_graph import lifecycle as L, run as R, reservation as RES


def sdk_client(monkeypatch, respond):
    client = bigquery.Client(project=L.PROJECT, location=L.LOCATION, credentials=AnonymousCredentials())
    def request(method, url, **kwargs):
        assert method == 'GET' and '/queries/' in url  # no unmocked cloud access
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(respond(urlparse(url).path, parse_qs(urlparse(url).query), kwargs)).encode()
        response.headers['content-type'] = 'application/json'
        return response
    monkeypatch.setattr(client._http, 'request', request)
    def query(sql, **kwargs):
        job = bigquery.QueryJob(kwargs['job_id'], sql, client)
        job._set_properties(dict(job._properties, status={'state': 'DONE'}))
        return job
    monkeypatch.setattr(client, 'query', query)
    return client


def page(n=None, token=None):
    result = {'jobComplete': True, 'totalRows': '3', 'schema': {'fields': [{'name': 'n', 'type': 'INTEGER'}]}}
    if n is not None:
        result['rows'] = [{'f': [{'v': str(n)}]}]
    if token:
        result['pageToken'] = token
    return result


def test_query_http_and_each_page_use_remaining_deadline(monkeypatch, tmp_path):
    clock, calls = [100.0], []
    monkeypatch.setattr(L.time, 'monotonic', lambda: clock[0])
    def respond(path, params, kwargs):
        calls.append(kwargs['timeout'])
        assert 0 < kwargs['timeout'] <= 100.5 - clock[0]
        if 'timeoutMs' in params:
            assert int(params['timeoutMs'][0]) <= (100.5 - clock[0]) * 1000
        clock[0] += .1
        return page() if params.get('maxResults') == ['0'] else page(len(calls), 'next' if len(calls) < 4 else None)
    client = sdk_client(monkeypatch, respond)
    window = L.WindowJobs('http', 100.5, tmp_path / 'jobs.json')
    rows = list(window.bind(client).query('SELECT n').result())
    assert len(rows) == 3 and len(calls) == 4
    assert calls[-1] < calls[0]


def test_stop_between_sdk_api_entry_and_http_dispatch_sends_nothing(monkeypatch, tmp_path):
    client = sdk_client(monkeypatch, lambda *args: pytest.fail('HTTP must not start after stop'))
    window = L.WindowJobs('dispatch', time.monotonic() + 60, tmp_path / 'jobs.json')
    connection_type = type(client._connection)
    dispatch = connection_type._do_request
    def stop_at_dispatch(self, *args, **kwargs):
        window.stop.set()
        return dispatch(self, *args, **kwargs)
    monkeypatch.setattr(connection_type, '_do_request', stop_at_dispatch)
    with pytest.raises(L.WindowStopped):
        window.bind(client).query('SELECT n').result()


@pytest.mark.parametrize('stop_by', ['event', 'deadline'])
@pytest.mark.parametrize('buffered', [False, True])
def test_no_lazy_page_or_buffered_row_after_stop(monkeypatch, tmp_path, stop_by, buffered):
    clock, calls = [100.0], []
    monkeypatch.setattr(L.time, 'monotonic', lambda: clock[0])
    def respond(path, params, kwargs):
        calls.append(params)
        result = page() if params.get('maxResults') == ['0'] else page(1, 'second')
        if buffered and 'rows' in result:
            result['rows'].append({'f': [{'v': '2'}]})
        return result
    client = sdk_client(monkeypatch, respond)
    window = L.WindowJobs('stopped', 101, tmp_path / 'jobs.json')
    rows = iter(window.bind(client).query('SELECT n').result())
    assert dict(next(rows)) == {'n': 1}
    before = len(calls)
    if stop_by == 'event':
        window.stop.set()
    else:
        clock[0] = 101
    with pytest.raises(L.WindowStopped):
        next(rows)
    assert len(calls) == before


@pytest.mark.parametrize('stop_by', ['deadline', 'event'])
def test_main_closes_capacity_while_real_sdk_page_is_still_blocked(monkeypatch, tmp_path, stop_by):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'evidence').mkdir()
    (tmp_path / 'fixtures').mkdir()
    (tmp_path / 'fixtures/cases.json').write_text('{}')
    windows, events, requests_at = [], [], []
    closed = threading.Event()
    real_window = L.WindowJobs
    def window(*args, **kwargs):
        w = real_window(*args, **kwargs)
        w.deadline = time.monotonic() + .25
        windows.append(w)
        return w
    def respond(path, params, kwargs):
        requests_at.append((path, params, windows[0].stop.is_set(), kwargs['timeout']))
        if params.get('maxResults') == ['0']:
            return page()
        if 'pageToken' not in params:
            return page(1, 'second')
        if params['pageToken'] == ['second']:
            events.append(('blocked-page', time.monotonic()))
            if stop_by == 'event':
                windows[0].stop.set()
            # Deliberately ignores the HTTP timeout and cancellation, but must be
            # released/joined even on the baseline failure (no orphan test worker).
            saw_close = closed.wait(2)
            events.append(('page-returned-after-close' if saw_close else 'page-returned-before-close', time.monotonic()))
            return page(2, 'third')
        return page(3)
    raw = sdk_client(monkeypatch, respond)
    def bq(*args):
        if args[0] == 'rm':
            events.append(('close', time.monotonic()))
            closed.set()
        return {'cmd': ' '.join(args), 'at': 'offline', 'rc': 0, 'stdout': '[]', 'stderr': ''}
    def opened(label):
        w = {'label': label, 'opened_at': 'offline', 'state': 'OPEN', 'steps': []}
        RES._save({'windows': [w], 'resources': []})
        return w
    def integration(client, *args):
        with L.window_executor(client, 1) as executor:
            executor.submit(lambda: list(client.query('SELECT n').result())).result()
    monkeypatch.setattr(R, 'WindowJobs', window)
    monkeypatch.setattr(R.bigquery, 'Client', lambda **kwargs: raw)
    monkeypatch.setattr(R, 'resolve_pointer', lambda *args: 'pin')
    monkeypatch.setattr(R, 'open_window', opened)
    monkeypatch.setattr(RES, '_bq', bq)
    monkeypatch.setattr(R, 'integration', integration)
    monkeypatch.setattr(L.WindowJobs, 'wait', lambda self, seconds: self.check())
    import subprocess
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: None)
    assert R.main(['run', 'integration', '--minutes', '1']) == 1
    names = [name for name, at in events]
    assert 'blocked-page' in names and 'page-returned-after-close' in names
    assert names.index('close') < names.index('page-returned-after-close')
    assert next(at for name, at in events if name == 'close') - windows[0].deadline < .5
    assert RES._load()['windows'][0]['verified_gone']
    assert not any(stopped for _, _, stopped, _ in requests_at)
    assert not any(params.get('pageToken') == ['third'] for _, params, _, _ in requests_at)
