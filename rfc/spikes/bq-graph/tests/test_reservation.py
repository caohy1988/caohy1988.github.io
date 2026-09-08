"""Astra P1#3: a failed cleanup must never be reported as verified deletion."""
import json
import pytest
import okf_bq_graph.reservation as R


def _run_close(monkeypatch, tmp_path, responses):
    monkeypatch.setattr(R, "MANIFEST", str(tmp_path / "m.json"))
    calls = []

    def fake_bq(*args):
        calls.append(args)
        key = " ".join(args)
        for k, v in responses:
            if k in key:
                return dict(v, cmd=key, at="t")
        return {"cmd": key, "rc": 1, "at": "t", "stdout": "", "stderr": "unexpected"}
    monkeypatch.setattr(R, "_bq", fake_bq)
    R._save({"project": "p", "location": "US", "windows": [{"label": "w", "steps": []}],
             "resources": [{"kind": "reservation", "window": "w", "name": "r", "state": "open"}]})
    w = R.close_window("w")
    return w, json.load(open(R.MANIFEST))


def test_transport_failure_is_delete_unverified(monkeypatch, tmp_path):
    w, m = _run_close(monkeypatch, tmp_path, [("", {"rc": 1, "stdout": "", "stderr": "transport unavailable"})])
    assert w["verified_gone"] is False and w["state"] == "DELETE_UNVERIFIED"
    assert m["resources"][0]["state"] == "DELETE_UNVERIFIED"


def test_retry_clears_outstanding_resource_only_after_verified_readback(monkeypatch, tmp_path):
    failed, manifest = _run_close(monkeypatch, tmp_path, [("", {"rc": 1, "stdout": "", "stderr": "offline"})])
    assert "deleted_at" not in manifest["resources"][0]
    assert "closed_at" not in failed
    monkeypatch.setattr(R, "_bq", lambda *args: {"cmd": " ".join(args), "rc": 0, "at": "retry", "stdout": "[]", "stderr": ""})
    closed = R.close_window("w", closer="safety-watcher")
    manifest = R._load()
    assert closed["verified_gone"] and closed["closed_by"] == "safety-watcher"
    assert len(manifest["windows"]) == 1
    assert manifest["resources"][0]["state"] == "deleted"
    assert manifest["resources"][0]["deleted_at"] == closed["closed_at"]
    assert closed["cleanup_attempts"][0]["errors"]
    assert not closed["cleanup_attempts"][-1]["errors"]


def test_still_listed_is_delete_unverified(monkeypatch, tmp_path):
    listed = json.dumps([{"name": f"projects/p/locations/US/reservations/{R.RESERVATION}"}])
    w, m = _run_close(monkeypatch, tmp_path, [
        ("ls --reservation_assignment", {"rc": 0, "stdout": "No reservation assignments found.", "stderr": ""}),
        ("rm --reservation", {"rc": 0, "stdout": "deleted", "stderr": ""}),
        ("ls --reservation", {"rc": 0, "stdout": listed, "stderr": ""}),
    ])
    assert w["verified_gone"] is False and "still listed" in " ".join(w["errors"])


def test_clean_delete_is_verified(monkeypatch, tmp_path):
    asg = json.dumps([{"name": f"projects/p/locations/US/reservations/{R.RESERVATION}/assignments/123"}])
    seen = {"n": 0}

    def ls_asg():
        seen["n"] += 1
        return {"rc": 0, "stdout": asg if seen["n"] == 1 else "No reservation assignments found.", "stderr": ""}
    responses = [
        ("rm --reservation_assignment", {"rc": 0, "stdout": "deleted", "stderr": ""}),
        ("rm --reservation", {"rc": 0, "stdout": "deleted", "stderr": ""}),
        ("ls --reservation_assignment", None),
        ("ls --reservation", {"rc": 0, "stdout": "No reservations found.", "stderr": ""}),
    ]
    import okf_bq_graph.reservation as RR
    monkeypatch.setattr(RR, "MANIFEST", str(tmp_path / "m.json"))

    def fake_bq(*args):
        key = " ".join(args)
        if "ls --reservation_assignment" in key:
            return dict(ls_asg(), cmd=key, at="t")
        for k, v in responses:
            if v and k in key:
                return dict(v, cmd=key, at="t")
        return {"cmd": key, "rc": 1, "at": "t", "stdout": "", "stderr": "unexpected"}
    monkeypatch.setattr(RR, "_bq", fake_bq)
    RR._save({"project": "p", "location": "US", "windows": [{"label": "w", "steps": []}],
              "resources": [{"kind": "reservation", "window": "w", "name": "r", "state": "open"}]})
    w = RR.close_window("w")
    assert w["verified_gone"] is True and w["state"] == "CLOSED_VERIFIED"
    assert json.load(open(RR.MANIFEST))["resources"][0]["state"] == "deleted"


def test_failed_job_cleanup_blocks_both_open_paths_until_reconciled(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from okf_bq_graph import safety, lifecycle as L, run
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'evidence').mkdir()
    R._save({'windows': [{'label': 'old', 'opened_at': '2026-09-06T01:00:00Z', 'steps': []}], 'resources': []})
    journal = tmp_path / 'evidence/jobs_old.json'
    journal.write_text(json.dumps({'label': 'old', 'project': L.PROJECT, 'location': L.LOCATION,
                                   'job_ids': ['unverified-old-job'], 'finished_job_ids': []}))
    calls = []
    def bq(*args):
        calls.append(args)
        return {'cmd': ' '.join(args), 'at': 'offline', 'rc': 0, 'stdout': '{} ' if args[0] == 'mk' else '[]', 'stderr': ''}
    monkeypatch.setattr(R, '_bq', bq)
    state = ['RUNNING']
    client = SimpleNamespace(cancel_job=lambda *a, **kw: None,
                             get_job=lambda *a, **kw: SimpleNamespace(state=state[0]))
    monkeypatch.setattr(safety.bigquery, 'Client', lambda **kw: client)
    assert not safety.cleanup('old', attempts=1)
    receipt = R._load()['windows'][0]
    assert receipt['verified_gone'] and receipt['closed_at']
    calls.clear()
    with pytest.raises(RuntimeError, match='job cleanup'):
        R.open_window('new')
    assert run.main(['run', 'integration', '--minutes', '1']) == 1
    assert calls == []
    assert json.loads(journal.read_text())['job_ids'] == ['unverified-old-job']
    state[0] = 'DONE'
    assert safety.cleanup('old', attempts=1)
    assert R._load()['windows'][0] == receipt  # capacity receipt is independently valid
    assert R.open_window('new')['state'] == 'OPEN'
    assert len([c for c in calls if c[0] == 'mk']) == 2


def test_concurrent_driver_and_watcher_delete_once(monkeypatch, tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr(R, 'MANIFEST', str(tmp_path / 'm.json'))
    R._save({'windows': [{'label': 'w', 'steps': []}], 'resources': []})
    first_read, second_started, release = threading.Event(), threading.Event(), threading.Event()
    calls = []
    def bq(*args):
        calls.append(args)
        if len(calls) == 1:
            first_read.set()
            assert release.wait(2)
        return {'cmd': ' '.join(args), 'at': 'offline', 'rc': 0, 'stdout': '[]', 'stderr': ''}
    monkeypatch.setattr(R, '_bq', bq)
    def watcher():
        second_started.set()
        return R.close_window('w', closer='safety-watcher')
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(R.close_window, 'w')
        assert first_read.wait(2)
        second = pool.submit(watcher)
        assert second_started.wait(2)
        try:
            with pytest.raises(TimeoutError):
                second.result(timeout=.05)
        finally:
            release.set()
        assert first.result()['verified_gone'] and second.result()['verified_gone']
    assert len([c for c in calls if c[0] == 'rm']) == 1


@pytest.mark.parametrize('damage', ['missing', 'new_job', 'wrong_label', 'partial', 'malformed', 'malformed_ids'])
def test_missing_or_stale_job_receipt_cannot_reopen(monkeypatch, tmp_path, damage):
    from types import SimpleNamespace
    from okf_bq_graph import lifecycle as L, run
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'evidence').mkdir()
    R._save({'windows': [{'label': 'old', 'opened_at': '2026-09-06T01:00:00Z',
                          'closed_at': '2026-09-06T01:01:00Z', 'verified_gone': True}], 'resources': []})
    journal = tmp_path / 'evidence/jobs_old.json'
    data = {'label': 'old', 'project': L.PROJECT, 'location': L.LOCATION, 'job_ids': ['j']}
    journal.write_text(json.dumps(data))
    client = SimpleNamespace(cancel_job=lambda *a, **kw: None,
                             get_job=lambda *a, **kw: SimpleNamespace(state='DONE'))
    L.cancel_journal(client, 'old', journal)
    receipt_path = journal.with_suffix('.cleanup.json')
    receipt = json.loads(receipt_path.read_text())
    if damage == 'missing':
        receipt_path.unlink()
    elif damage == 'new_job':
        journal.write_text(json.dumps(dict(data, job_ids=['j', 'late'])))
    elif damage == 'malformed':
        receipt_path.write_text('[]')
    elif damage == 'malformed_ids':
        journal.write_text(json.dumps(dict(data, job_ids='')))
        receipt_path.write_text(json.dumps(dict(receipt, job_ids='', verified_done_job_ids='')))
    else:
        receipt['label' if damage == 'wrong_label' else 'verified_done_job_ids'] = 'wrong' if damage == 'wrong_label' else []
        receipt_path.write_text(json.dumps(receipt))
    monkeypatch.setattr(R, '_bq', lambda *args: pytest.fail('must not create capacity'))
    with pytest.raises(RuntimeError, match='job cleanup'):
        R.open_window('new')
    assert run.main(['run', 'integration', '--minutes', '1']) == 1


def _verified_pair(tmp_path, directory, label):
    """A journal + verified cleanup receipt for `label`, written into `directory`."""
    from types import SimpleNamespace
    from okf_bq_graph import lifecycle as L
    directory.mkdir(parents=True, exist_ok=True)
    journal = directory / f'jobs_{label}.json'
    journal.write_text(json.dumps({'label': label, 'project': L.PROJECT, 'location': L.LOCATION, 'job_ids': ['j']}))
    client = SimpleNamespace(cancel_job=lambda *a, **kw: None,
                             get_job=lambda *a, **kw: SimpleNamespace(state='DONE'))
    L.cancel_journal(client, label, journal)
    return journal


@pytest.mark.xfail(strict=True, reason="KNOWN DEFECT (Slice B live attempt 2026-09-08): open_window() takes no "
                                       "evidence_dir and re-gates against MANIFEST's own directory, so a controller "
                                       "configured with --gql-evidence-dir is refused at open. Remove this marker "
                                       "with the fix; strict=True makes an unnoticed fix fail loudly.")
def test_open_window_reads_receipts_from_the_evidence_dir_it_was_given(monkeypatch, tmp_path):
    """A reconciled window's receipts gate the open from wherever the caller staged them.

    The controller preflights against its configured `evidence_dir`; if the opener re-gates against the manifest's own
    directory instead, a run whose receipts were reconciled into a subdirectory (PR50) is refused for a window whose
    cleanup IS verified, and no live window can ever open."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'evidence').mkdir()
    R._save({'windows': [{'label': 'old', 'opened_at': '2026-09-06T01:00:00Z',
                          'closed_at': '2026-09-06T01:01:00Z', 'verified_gone': True}], 'resources': []})
    staged = tmp_path / 'evidence' / 'legacy-reconcile'
    _verified_pair(tmp_path, staged, 'old')
    monkeypatch.setattr(R, '_bq', lambda *args: pytest.fail('must not create capacity'))
    # the manifest's own directory holds no receipt for `old`, so the default gate still refuses
    with pytest.raises(RuntimeError, match='job cleanup'):
        R.open_window('new')
    monkeypatch.setattr(R, '_bq', lambda *args: {'cmd': ' '.join(args), 'rc': 0, 'at': 't', 'stdout': '{}', 'stderr': ''})
    assert R.open_window('new', evidence_dir=str(staged))['state'] == 'OPEN'


@pytest.mark.xfail(strict=True, reason="KNOWN DEFECT (see above): open_window() takes no evidence_dir. This case "
                                       "pins the safety half of the fix - naming a directory must never waive the "
                                       "check - so the fix cannot be landed as a bypass.")
def test_open_window_evidence_dir_relaxes_nothing(monkeypatch, tmp_path):
    """Naming a directory is not a waiver: an unverified receipt there refuses exactly as the default does."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'evidence').mkdir()
    R._save({'windows': [{'label': 'old', 'opened_at': '2026-09-06T01:00:00Z',
                          'closed_at': '2026-09-06T01:01:00Z', 'verified_gone': True}], 'resources': []})
    staged = tmp_path / 'evidence' / 'legacy-reconcile'
    journal = _verified_pair(tmp_path, staged, 'old')
    journal.with_suffix('.cleanup.json').unlink()
    monkeypatch.setattr(R, '_bq', lambda *args: pytest.fail('must not create capacity'))
    with pytest.raises(RuntimeError, match='job cleanup is unverified for old'):
        R.open_window('new', evidence_dir=str(staged))


@pytest.mark.xfail(strict=True, reason="KNOWN DEFECT (Slice B live attempt 2026-09-08): safety.cleanup() hardcodes "
                                       "'evidence/jobs_<label>.json', so the DETACHED watcher cannot read a journal "
                                       "staged under a configured --gql-evidence-dir. Observed live in "
                                       "evidence/watcher_chain-gql-b-20260908.jsonl as FileNotFoundError on all three "
                                       "attempts. This is the safety-critical half: capacity closes while job cleanup "
                                       "fails, which is exactly 'capacity deletion is not job cleanup'.")
def test_safety_watcher_reads_the_journal_from_the_configured_evidence_dir(monkeypatch, tmp_path):
    """The independent closer must cancel the jobs the window actually journaled, wherever they were journaled.

    The watcher is a different process spawned with only a label; if it resolves the journal against a directory the
    window never used, it reports every owned job as unreadable and no cancellation is even attempted."""
    from types import SimpleNamespace
    from okf_bq_graph import lifecycle as L, safety
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'evidence').mkdir()
    R._save({'windows': [{'label': 'w', 'steps': []}], 'resources': []})
    staged = tmp_path / 'evidence' / 'legacy-reconcile'
    staged.mkdir(parents=True)
    (staged / 'jobs_w.json').write_text(json.dumps(
        {'label': 'w', 'project': L.PROJECT, 'location': L.LOCATION, 'job_ids': ['j']}))
    monkeypatch.setattr(R, '_bq', lambda *args: {'cmd': ' '.join(args), 'rc': 0, 'at': 't', 'stdout': '[]', 'stderr': ''})
    monkeypatch.setattr(safety.bigquery, 'Client', lambda **kw: SimpleNamespace(
        cancel_job=lambda *a, **kw: None, get_job=lambda *a, **kw: SimpleNamespace(state='DONE')))
    assert safety.cleanup('w', attempts=1, evidence_dir=str(staged))
