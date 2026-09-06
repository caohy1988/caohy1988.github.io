"""Astra P1#3: a failed cleanup must never be reported as verified deletion."""
import json
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
