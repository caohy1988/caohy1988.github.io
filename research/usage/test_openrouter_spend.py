#!/usr/bin/env python3
"""OpenRouter spend card: GET /api/v1/key with the key from ~/.dsh/.env (shared by DSH, Qwen Code and OpenCode GLM-5.3).

    python3 test_openrouter_spend.py

A fake key in a temp HOME and a stubbed HTTP call; never reads the real ~/.dsh/.env, never touches the
network, the real CLIs, or the real snapshot.json / index.html. The fake key must never reach the
output, the page, an error string or stdout.
"""
import contextlib
import copy
import io
import json
import os
import socket
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_and_build as cab  # noqa: E402

REAL = {name: getattr(cab, name) for name in ("collect_openrouter", "_openrouter_get", "main")}
KEY = "sk-or-v1-FAKEFAKEFAKE0123456789abcdef0123456789"
PAYLOAD = {"data": {"label": "sk-or-v1-FAK...789", "limit": None, "limit_remaining": None, "limit_reset": None,
                    "usage": 12.3456, "usage_daily": 0.25, "usage_weekly": 1.5, "usage_monthly": 4.75,
                    "byok_usage": 0, "is_free_tier": False}}
WINDOWS = ("today_utc", "week_utc", "month_utc", "all_time")


def page(**seats):
    """render_html() of a minimal snapshot (the seats render_html requires, empty) plus `seats`."""
    snap = {"refreshed_at": "x", "claude": {}, "codex": {}, "kimi": {}, "agy": {}, "grok": {}}
    snap.update(seats)
    return cab.render_html(snap)


def card(html):
    start = html.index('<section class="card" id="openrouter">')
    return html[start:html.index("</section>", start)]


class Home:
    """A temp HOME whose ~/.dsh/.env holds `env_text` (None: no file)."""

    def __init__(self, env_text):
        self.env_text = env_text

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        home = Path(self.tmp.name)
        if self.env_text is not None:
            (home / ".dsh").mkdir()
            (home / ".dsh" / ".env").write_text(self.env_text)
        self.patch = mock.patch.dict(os.environ, {"HOME": str(home)})
        self.patch.start()
        return home

    def __exit__(self, *exc):
        self.patch.stop()
        self.tmp.cleanup()
        return False


def collect(env_text="OPENROUTER_API_KEY=" + KEY + "\n", reply=None, raises=None, now=None):
    """collect_openrouter() with a stubbed HTTP call; returns (seat, calls)."""
    calls = []

    def fake_get(url, api_key, timeout=15):
        calls.append((url, api_key))
        if raises is not None:
            raise raises
        return copy.deepcopy(PAYLOAD if reply is None else reply)

    with Home(env_text), mock.patch.object(cab, "_openrouter_get", fake_get):
        return REAL["collect_openrouter"](now=now), calls


def assert_no_key(test, *blobs):
    for blob in blobs:
        text = blob if isinstance(blob, str) else json.dumps(blob)
        test.assertNotIn(KEY, text)
        test.assertNotIn("FAKEFAKE", text)


class ReadKeyTests(unittest.TestCase):
    def read(self, env_text):
        with Home(env_text) as home:
            return cab.read_openrouter_key(home / ".dsh" / ".env")

    def test_dotenv_forms(self):
        for text in (f"OPENROUTER_API_KEY={KEY}\n", f'export OPENROUTER_API_KEY="{KEY}"\n',
                     f"OPENROUTER_API_KEY='{KEY}'  # shared with qwen-or\n", f"OPENROUTER_API_KEY = {KEY} # note\n",
                     f"DEEPSEEK_API_KEY=other\nOPENROUTER_API_KEY={KEY}\r\n",
                     f"OPENROUTER_API_KEY=sk-or-v1-old-old-old\nOPENROUTER_API_KEY={KEY}\n"):  # last one wins
            self.assertEqual(self.read(text), KEY, text)

    def test_no_usable_key(self):
        for text in (None, "", "DEEPSEEK_API_KEY=x\n", "OPENROUTER_API_KEY=\n", 'OPENROUTER_API_KEY=""\n',
                     "OPENROUTER_API_KEY=$OTHER_KEY\n", "# OPENROUTER_API_KEY=" + KEY + "\n",
                     f"OPENROUTER_API_KEY={KEY}\nOPENROUTER_API_KEY=\n"):  # the last assignment empties it
            self.assertIsNone(self.read(text), text)


class CollectTests(unittest.TestCase):
    def test_spend_from_the_key_endpoint(self):
        seat, calls = collect()
        self.assertEqual(calls, [(cab.OPENROUTER_KEY_URL, KEY)])
        self.assertEqual(cab.OPENROUTER_KEY_URL, "https://openrouter.ai/api/v1/key")
        self.assertTrue(seat["ok"], seat)
        self.assertEqual(seat["spend_usd"], {"today_utc": 0.25, "week_utc": 1.5, "month_utc": 4.75,
                                             "all_time": 12.3456})
        self.assertEqual(seat["seats"], ["DSH", "Qwen Code", "OpenCode (GLM-5.3)"])
        self.assertIn("shared-key totals", seat["scope"])
        self.assertIn("OpenCode (GLM-5.3)", seat["scope"])
        self.assertNotIn("label", json.dumps(seat))  # the key label (a masked key) is never published
        self.assertNotIn("error", seat)
        assert_no_key(self, seat)

    def test_key_limit_is_published_when_set(self):
        reply = copy.deepcopy(PAYLOAD)
        reply["data"].update(limit=50, limit_remaining=37.66, limit_reset="monthly")
        seat, _ = collect(reply=reply)
        self.assertEqual((seat["limit_usd"], seat["limit_remaining_usd"], seat["limit_reset"]), (50, 37.66, "monthly"))

    def test_failures_are_unavailable_never_zero(self):
        http401 = urllib.error.HTTPError(cab.OPENROUTER_KEY_URL, 401, "Unauthorized " + KEY, {}, None)
        cases = [
            (dict(env_text=None), "OPENROUTER_API_KEY not found in ~/.dsh/.env"),
            (dict(env_text="DEEPSEEK_API_KEY=x\n"), "OPENROUTER_API_KEY not found in ~/.dsh/.env"),
            (dict(raises=http401), "HTTP 401"),
            (dict(raises=urllib.error.URLError("no route " + KEY)), "request failed"),
            (dict(raises=socket.timeout("timed out")), "request failed"),
            (dict(raises=TimeoutError()), "request failed"),
            (dict(raises=ValueError("Expecting value " + KEY)), "response unreadable"),
            (dict(reply={"error": {"message": "nope"}}), "response unreadable"),
            (dict(reply={"data": dict(PAYLOAD["data"], usage=None)}), "response unreadable"),
            (dict(reply={"data": dict(PAYLOAD["data"], usage_daily="0.25")}), "response unreadable"),
            (dict(reply={"data": dict(PAYLOAD["data"], usage_weekly=-1)}), "response unreadable"),
            (dict(reply={"data": dict(PAYLOAD["data"], usage_monthly=float("nan"))}), "response unreadable"),
            (dict(reply={"data": dict(PAYLOAD["data"], usage=True)}), "response unreadable"),
            (dict(reply=["not", "a", "dict"]), "response unreadable"),
        ]
        for kw, want in cases:
            seat, calls = collect(**kw)
            self.assertFalse(seat["ok"], kw)
            self.assertIn(want, seat["error"], kw)
            self.assertEqual(seat["spend_usd"], dict.fromkeys(WINDOWS), kw)
            self.assertEqual(len(calls), 0 if "env_text" in kw else 1, kw)
            body = card(page(openrouter=seat))
            self.assertIn("unavailable", body, kw)
            self.assertNotIn("$0", body, kw)
            assert_no_key(self, seat, body)

    def test_zero_spend_after_a_good_fetch_is_zero(self):
        reply = {"data": dict(PAYLOAD["data"], usage=0, usage_daily=0, usage_weekly=0, usage_monthly=0)}
        seat, _ = collect(reply=reply)
        self.assertTrue(seat["ok"])
        body = card(page(openrouter=seat))
        self.assertEqual(body.count("$0.00"), 4)
        self.assertNotIn("unavailable", body)


class RenderTests(unittest.TestCase):
    def test_card_says_combined_and_shows_each_window(self):
        seat, _ = collect(now=datetime(2026, 10, 25, 3, 0, tzinfo=timezone.utc))  # a Sunday, 10-24 20:00 PT
        html = page(openrouter=seat)
        body = card(html)
        for text in ("Shared-key totals: DSH, Qwen Code and OpenCode (GLM-5.3)", "not split per seat", "$0.2500", "$1.50", "$4.75", "$12.35",
                     "Day 2026-10-25 (UTC)", "Week from Mon 2026-10-19 (UTC)", "Month 2026-10 (UTC)", "All time",
                     "Fetched 2026-10-24 20:00:00 PDT"):
            self.assertIn(text, body, text)
        for word in ("Today", "This week", "This month", "currently"):  # dated labels only: the page stays static
            self.assertNotIn(word, body, word)
        # both seat cards point at the shared-key card instead of repeating the figure
        for seat_id in ("dsh", "qwen"):
            start = html.index(f'id="{seat_id}">')
            self.assertIn("OpenRouter spend card", html[start:html.index("</section>", start)], seat_id)

    def test_missing_seat_renders_unavailable(self):
        body = card(page())
        self.assertIn("unavailable", body)
        self.assertNotIn("$0", body)


class HttpTests(unittest.TestCase):
    def test_key_travels_only_in_an_unredirected_header(self):
        seen = {}

        class FakeResponse(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class FakeOpener:
            def open(self, req, timeout=None):
                seen.update(req=req, timeout=timeout)
                return FakeResponse(json.dumps(PAYLOAD).encode())

        def fake_build_opener(*handlers):
            seen["handlers"] = handlers
            return FakeOpener()

        with mock.patch.object(cab.urllib.request, "build_opener", fake_build_opener):
            got = REAL["_openrouter_get"](cab.OPENROUTER_KEY_URL, KEY)
        self.assertEqual(got, PAYLOAD)
        req = seen["req"]
        self.assertEqual((req.full_url, req.get_method()), ("https://openrouter.ai/api/v1/key", "GET"))
        self.assertEqual(req.unredirected_hdrs.get("Authorization"), "Bearer " + KEY)
        self.assertNotIn("Authorization", req.headers)  # urllib copies only these onto a redirect
        self.assertTrue(seen["timeout"])
        self.assertTrue(any(isinstance(h, type) and issubclass(h, urllib.request.HTTPRedirectHandler)
                            for h in seen["handlers"]))

    @unittest.skipUnless(Path("/etc/ssl/cert.pem").is_file(), "needs the macOS system CA bundle")
    def test_tls_verifies_with_ca_certificates_on_every_interpreter(self):
        # python.org builds ship no CA certificates; the context must still verify (never CERT_NONE)
        ctx = cab._https_context()
        self.assertEqual((ctx.verify_mode, ctx.check_hostname), (cab.ssl.CERT_REQUIRED, True))
        self.assertGreater(ctx.cert_store_stats()["x509_ca"], 0)

    def test_redirects_are_refused(self):
        handler = cab._NoRedirect()
        req = urllib.request.Request(cab.OPENROUTER_KEY_URL)
        self.assertIsNone(handler.redirect_request(req, None, 302, "Found", {}, "https://elsewhere.example/"))


class MainTests(unittest.TestCase):
    def test_main_publishes_the_card_without_the_key(self):
        seat, _ = collect()
        names = [n for n in dir(cab) if n.startswith("collect_") and callable(getattr(cab, n))]
        stubs = {n: (lambda: {}) for n in names}
        stubs["collect_openrouter"] = lambda: copy.deepcopy(seat)
        with tempfile.TemporaryDirectory() as d, mock.patch.multiple(cab, HERE=Path(d), **stubs), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            REAL["main"]()
            snap_text = (Path(d) / "snapshot.json").read_text()
            html = (Path(d) / "index.html").read_text()
        snap = json.loads(snap_text)
        self.assertEqual(snap["openrouter"]["spend_usd"]["month_utc"], 4.75)
        self.assertIn("$4.75", card(html))
        self.assertIn("OpenRouter: ok=True", out.getvalue())
        assert_no_key(self, snap_text, html, out.getvalue())


if __name__ == "__main__":
    unittest.main()
