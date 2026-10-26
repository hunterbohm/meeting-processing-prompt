from __future__ import annotations

import copy
import datetime
import html
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import review_form

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "review_form.py"
EXAMPLE = json.loads((HERE / "example-review.json").read_text())
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
    "base-uri 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)


class FormFields(HTMLParser):
    """What a browser sends for the page's untouched form, plus the values each radio group offers."""

    def __init__(self, page: str) -> None:
        super().__init__()
        self.fields: dict[str, str] = {}
        self.choices: dict[str, list[str]] = {}
        self._textarea: str | None = None
        self.feed(page)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "input" and a.get("type") == "radio":
            self.choices.setdefault(a["name"], []).append(a["value"])
            if "checked" in a:
                self.fields[a["name"]] = a["value"]
        elif tag == "input" and "name" in a:
            self.fields[a["name"]] = a.get("value") or ""
        elif tag == "textarea":
            self._textarea = a["name"]
            self.fields[self._textarea] = ""

    def handle_data(self, data: str) -> None:
        if self._textarea:
            self.fields[self._textarea] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "textarea":
            self._textarea = None


class PrefixStrippingProxy(BaseHTTPRequestHandler):
    """Stands in for `tailscale serve --set-path /review`: strips the prefix, keeps Host, never follows redirects."""

    def do_GET(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        path = self.path[len("/review"):] if self.path.startswith("/review/") else self.path
        backend = http.client.HTTPConnection(*self.server.backend, timeout=10)
        backend.request(self.command, path, body, dict(self.headers))
        reply = backend.getresponse()
        data = reply.read()
        backend.close()
        self.send_response_only(reply.status)
        for name, value in reply.getheaders():
            if name.lower() not in ("connection", "date", "server"):
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    do_POST = do_GET

    def log_message(self, *args: Any) -> None:
        pass


def setUpModule() -> None:
    review_form.Handler.log_message = lambda *args: None


class ReviewFormTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.data = self.tmp / "data"
        server = review_form.Server("127.0.0.1", 0, review_form.Store(self.data))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.base = f"http://127.0.0.1:{server.server_address[1]}"

    def cli(self, *args: str, base: str | None = None) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if not k.startswith("REVIEW_FORM_")}
        env["REVIEW_FORM_DATA"] = str(self.data)
        if base is not None:
            env["REVIEW_FORM_BASE_URL"] = base
        return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=60)

    def publish(self, review: Any, base: str | None = None) -> subprocess.CompletedProcess:
        path = self.tmp / "review.json"
        path.write_text(json.dumps(review))
        return self.cli("publish", str(path), base=self.base if base is None else base)

    def published_url(self, review: Any = EXAMPLE, base: str | None = None) -> str:
        result = self.publish(review, base)
        self.assertEqual(result.returncode, 0, f"publish succeeds: {result.stderr}")
        self.assertEqual(result.stdout.count("\n"), 1, "publish prints the link alone")
        return result.stdout.strip()

    def published_form(self, review: Any = EXAMPLE) -> tuple[str, str, dict[str, str]]:
        url = self.published_url(review)
        status, _, page = self.get(url)
        self.assertEqual(status, 200, "published link opens")
        return url, url.rsplit("/", 1)[1], FormFields(page).fields

    def show(self, slug: str, base: str | None = None) -> dict:
        result = self.cli("show", slug, base=base)
        self.assertEqual(result.returncode, 0, f"show succeeds: {result.stderr}")
        return json.loads(result.stdout)

    def saved(self) -> list[str]:
        return sorted(p.name for p in self.data.iterdir()) if self.data.exists() else []

    def get(self, url: str) -> tuple[int, Any, str]:
        return self._open(urllib.request.Request(url))

    def post(self, url: str, fields: dict[str, str], origin: str | None = None) -> tuple[int, Any, str]:
        request = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode())
        origin = self.base if origin is None else origin
        if origin:
            request.add_header("Origin", origin)
        return self._open(request)

    @staticmethod
    def _open(request: urllib.request.Request) -> tuple[int, Any, str]:
        try:
            with OPENER.open(request, timeout=10) as r:
                return r.status, r.headers, r.read().decode()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.headers, e.read().decode()

    def test_publish_rejects_invalid_reviews(self) -> None:
        no_date = copy.deepcopy(EXAMPLE)
        del no_date["meeting"]["date"]
        duplicate_id = copy.deepcopy(EXAMPLE)
        duplicate_id["tasks"][1]["id"] = "1"
        bad_due = copy.deepcopy(EXAMPLE)
        bad_due["tasks"][0]["due"] = "2026-02-30"
        cases = [("missing date", no_date, "meeting.date"), ("duplicate task id", duplicate_id, "tasks[1].id"),
                 ("bad due date", bad_due, "tasks[0].due"), ("not an object", [], "review")]
        for name, review, path in cases:
            with self.subTest(name):
                result = self.publish(review)
                self.assertEqual(result.returncode, 1, "invalid review exits 1")
                self.assertEqual(result.stdout, "", "invalid review prints nothing to stdout")
                self.assertIn(path, result.stderr, "stderr names the bad field")
        self.assertEqual(self.saved(), [], "no invalid review was saved")

    def test_published_link_serves_the_escaped_form(self) -> None:
        review = copy.deepcopy(EXAMPLE)
        review["tasks"][2]["title"] = "Fix <script>alert(1)</script> in the footer"
        url = self.published_url(review)
        self.assertTrue(url.startswith(self.base + "/"), "link is under the base URL")
        status, _, page = self.get(url)
        self.assertEqual(status, 200, "link opens")
        texts = [review["meeting"]["title"], *(t["title"] for t in review["tasks"]), *(q["text"] for q in review["questions"])]
        for text in texts:
            self.assertIn(html.escape(text), page, f"page shows {text!r}")
        self.assertNotIn("<script>", page, "task title markup is escaped")
        self.assertIn("Mon, Oct 26 · Dana Lee, Sam Ortiz · Website rebuild", page, "meta line shows date, people, project")
        self.assertEqual(page.count("no project"), 1, "only the task whose project differs is tagged")

    def test_publish_without_a_reachable_server_keeps_nothing(self) -> None:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            closed = f"http://127.0.0.1:{s.getsockname()[1]}"
        for name, base in [("server not running", closed), ("no base URL", "")]:
            with self.subTest(name):
                result = self.publish(EXAMPLE, base=base)
                self.assertEqual(result.returncode, 1, "publish exits 1")
                self.assertEqual(result.stdout, "", "publish prints nothing to stdout")
                self.assertIn(closed if base else "REVIEW_FORM_BASE_URL", result.stderr, "stderr says what failed")
        self.assertEqual(self.saved(), [], "the unreachable review was deleted")

    def test_submission_is_saved_in_the_readme_shape(self) -> None:
        url = self.published_url()
        slug = url.rsplit("/", 1)[1]
        before = self.show(slug)
        self.assertEqual((before["url"], before["response"]), (None, None), "no url without base URL, no response yet")
        form = FormFields(self.get(url)[2])
        fields, choices = form.fields, form.choices
        self.assertEqual(choices["task.2.keep"], ["keep", "drop"], "each task offers keep and drop")
        self.assertEqual(choices["q.q1"], EXAMPLE["questions"][0]["options"], "option question offers its options")
        fields.update({
            "task.1.title": "  Send Dana the final scope  ",
            "task.1.note": "Attach the PDF",
            "task.2.keep": "drop",
            "task.3.title": "",
            "task.3.due": "2026-11-02",
            "q.q1": "New project",
            "q.q2": "  Northwind Studio  ",
            "notes": "Call Sam on Monday",
        })
        status, headers, _ = self.post(url, fields)
        self.assertEqual(status, 303, "submit redirects")
        self.assertEqual(urllib.parse.urljoin(url, headers["Location"]), url, "redirect returns to the review link")
        shown = self.show(slug, base=self.base)
        self.assertEqual(shown["slug"], slug)
        self.assertEqual(shown["url"], url, "show gives the link")
        self.assertEqual(shown["review"], EXAMPLE, "show returns the review as published, unknown keys included")
        response = shown["response"]
        submitted_at = datetime.datetime.strptime(response.pop("submitted_at"), "%Y-%m-%dT%H:%M:%SZ")
        age = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - submitted_at
        self.assertLess(abs(age.total_seconds()), 300, "submitted_at is the current UTC time")
        self.assertEqual(response, {
            "tasks": [
                {"id": "1", "keep": True, "title": "Send Dana the final scope", "due": "2026-10-30", "note": "Attach the PDF"},
                {"id": "2", "keep": False, "title": "Move the launch date to November 12 in the plan", "due": None, "note": ""},
                {"id": "3", "keep": True, "title": "Share the brand guide with Sam", "due": "2026-11-02", "note": ""},
            ],
            "answers": {"q1": "New project", "q2": "Northwind Studio"},
            "notes": "Call Sam on Monday",
        })

    def test_second_submission_is_refused(self) -> None:
        url, slug, fields = self.published_form()
        self.assertEqual(self.post(url, fields)[0], 303, "first submit is accepted")
        stored = self.show(slug)["response"]
        self.assertEqual(self.post(url, dict(fields, notes="second try"))[0], 409, "second submit is refused")
        self.assertEqual(self.post(url, dict(fields, **{"task.1.due": "nope"}))[0], 409,
                         "an invalid second submit is refused as already sent, not as invalid")
        self.assertEqual(self.show(slug)["response"], stored, "stored response is unchanged")

    def test_concurrent_submissions_have_one_winner(self) -> None:
        url, slug, fields = self.published_form()
        barrier = threading.Barrier(8)
        statuses: dict[str, int] = {}

        def submit(note: str) -> None:
            barrier.wait()
            statuses[note] = self.post(url, dict(fields, notes=note))[0]

        threads = [threading.Thread(target=submit, args=(f"try {i}",)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        winners = [note for note, status in statuses.items() if status == 303]
        self.assertEqual(len(winners), 1, f"exactly one concurrent submit wins: {statuses}")
        self.assertEqual(sorted(statuses.values()), [303] + [409] * 7, "the rest are refused")
        self.assertEqual(self.show(slug)["response"]["notes"], winners[0], "the winner's answers are stored")

    def test_cross_site_posts_are_refused(self) -> None:
        url, slug, fields = self.published_form()
        for name, origin in [("foreign origin", "https://evil.example"), ("no origin", ""), ("null origin", "null")]:
            with self.subTest(name):
                self.assertEqual(self.post(url, fields, origin=origin)[0], 403, "refused")
        self.assertIsNone(self.show(slug)["response"], "nothing was stored")

    def test_invalid_values_are_refused(self) -> None:
        url, slug, fields = self.published_form()
        without_keep = {k: v for k, v in fields.items() if k != "task.1.keep"}
        cases = [
            ("choice not offered", dict(fields, **{"q.q1": "Maybe"}), "q.q1"),
            ("impossible date", dict(fields, **{"task.1.due": "2026-02-30"}), "task.1.due"),
            ("keep is not keep or drop", dict(fields, **{"task.1.keep": "later"}), "task.1.keep"),
            ("keep missing", without_keep, "task.1.keep"),
            ("note too long", dict(fields, **{"task.1.note": "x" * 5001}), "task.1.note"),
        ]
        for name, body, field in cases:
            with self.subTest(name):
                status, _, page = self.post(url, body)
                self.assertEqual(status, 400, "refused as invalid")
                self.assertIn(field, page, "error page names the field")
        self.assertIsNone(self.show(slug)["response"], "nothing was stored")

    def test_review_works_under_a_path_prefix_and_unknown_links_404(self) -> None:
        url = self.published_url(base=self.base + "/review/")
        self.assertTrue(url.startswith(self.base + "/review/"), "trailing slash on the base URL is dropped")
        status, _, page = self.get(url)
        self.assertEqual(status, 200, "prefixed link opens")
        status, headers, _ = self.post(url, FormFields(page).fields)
        self.assertEqual(status, 303, "prefixed submit is accepted")
        self.assertEqual(urllib.parse.urljoin(url, headers["Location"]), url, "redirect keeps the prefix")
        for path in ["/review/AAAAAAAAAAAAAAAAAAAAAA", "/review/short", "/review/..%2F..%2Fetc%2Fpasswd", "/"]:
            with self.subTest(path):
                self.assertEqual(self.get(self.base + path)[0], 404, "unknown link is not found")
        self.assertEqual(self.cli("show", "AAAAAAAAAAAAAAAAAAAAAA").returncode, 1, "show of an unknown slug exits 1")

    def test_review_works_behind_a_prefix_stripping_proxy(self) -> None:
        proxy = ThreadingHTTPServer(("127.0.0.1", 0), PrefixStrippingProxy)
        proxy.backend = ("127.0.0.1", int(self.base.rsplit(":", 1)[1]))
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        self.addCleanup(proxy.server_close)
        self.addCleanup(proxy.shutdown)
        public = f"http://127.0.0.1:{proxy.server_address[1]}"
        url = self.published_url(base=public + "/review")
        status, _, page = self.get(url)
        self.assertEqual(status, 200, "link opens through the proxy")
        status, headers, _ = self.post(url, FormFields(page).fields, origin=public)
        self.assertEqual(status, 303, "submit through the proxy is accepted, so Origin matched the forwarded Host")
        self.assertEqual(urllib.parse.urljoin(url, headers["Location"]), url, "redirect keeps the stripped prefix")
        self.assertIn("Sent.", self.get(url)[2], "the link shows the sent page")

    def test_serve_refuses_non_loopback_hosts(self) -> None:
        for host in ["0.0.0.0", "192.168.1.10", "::", "localhost"]:
            with self.subTest(host):
                result = self.cli("serve", "--host", host, "--port", "0")
                self.assertEqual(result.returncode, 2, "serve exits 2")
                self.assertIn(host, result.stderr, "stderr names the refused host")

    def test_serve_command_serves_what_publish_saved(self) -> None:
        env = {k: v for k, v in os.environ.items() if not k.startswith("REVIEW_FORM_")}
        env.update(REVIEW_FORM_DATA=str(self.data), REVIEW_FORM_PORT="0")
        proc = subprocess.Popen([sys.executable, str(SCRIPT), "serve"], env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True)
        self.addCleanup(proc.stdout.close)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        line = proc.stdout.readline()
        self.assertIn("http://127.0.0.1:", line, "serve says where it listens")
        served = line.split("http://", 1)[1].split()[0]
        url = self.published_url(base=f"http://{served}")
        self.assertEqual(self.get(url)[0], 200, "the serve command serves the published review")

    def test_after_submission_the_link_shows_what_was_sent(self) -> None:
        url, _, fields = self.published_form()
        fields.update({"task.2.keep": "drop", "q.q1": "New project"})
        self.assertEqual(self.post(url, fields)[0], 303, "submit is accepted")
        status, _, page = self.get(url)
        self.assertEqual(status, 200, "link still opens")
        self.assertIn("Sent.", page, "sent page is shown")
        self.assertNotIn("<form", page, "the form is gone")
        self.assertIn("2 kept · 1 dropped", page, "sent page counts kept and dropped")
        self.assertIn("Send Dana the revised scope", page, "kept title is listed")
        self.assertIn("due Fri, Oct 30", page, "kept due date is listed")
        self.assertNotIn("Move the launch date", page, "dropped title is not listed")
        self.assertIn("New project", page, "answer is listed")

    def test_meeting_without_tasks_or_questions(self) -> None:
        review = copy.deepcopy(EXAMPLE)
        review["tasks"] = []
        del review["questions"]
        url, slug, fields = self.published_form(review)
        status, _, page = self.get(url)
        self.assertNotIn("<h2>Tasks", page, "no task heading")
        self.assertIn("No tasks", page, "says there are no tasks")
        self.assertEqual(self.post(url, dict(fields, notes="All good"))[0], 303, "submit is accepted")
        response = self.show(slug)["response"]
        self.assertEqual((response["tasks"], response["answers"], response["notes"]), ([], {}, "All good"))

    def test_every_response_sends_the_security_headers(self) -> None:
        url, _, fields = self.published_form()
        responses = {
            "form": self.get(url),
            "not found": self.get(self.base + "/nope"),
            "refused post": self.post(url, fields, origin="https://evil.example"),
            "wrong method": self._open(urllib.request.Request(url, method="DELETE")),
        }
        for name, (_, headers, _) in responses.items():
            for header, value in SECURITY_HEADERS.items():
                self.assertEqual(headers[header], value, f"{name} sends {header}")


if __name__ == "__main__":
    unittest.main()
