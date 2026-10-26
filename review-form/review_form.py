#!/usr/bin/env python3
"""Meeting review forms for your phone. README.md is the contract."""

from __future__ import annotations

import argparse
import datetime
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html import escape as esc
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ID_RE = re.compile(r"[A-Za-z0-9_-]+")
SLUG_RE = re.compile(r"[A-Za-z0-9_-]{16,64}")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
MAX_TEXT = 5000
MAX_BODY = 64 * 1024
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
    "base-uri 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    # Not no-referrer: under it, browsers send `Origin: null` on the form POST and the Origin check refuses it.
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex",
}
TYPE_NAMES = {str: "a string", list: "an array", dict: "an object"}
ALREADY_SENT = "This review was already sent. Open its link to see what was sent."


@dataclass(frozen=True)
class Meeting:
    title: str
    date: str
    people: tuple[str, ...]
    summary: str
    project: str | None


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    detail: str
    project: str | None
    due: str | None


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    options: tuple[str, ...]


@dataclass(frozen=True)
class Review:
    meeting: Meeting
    tasks: tuple[Task, ...]
    questions: tuple[Question, ...]


def is_date(value: str) -> bool:
    try:
        return bool(DATE_RE.fullmatch(value)) and bool(datetime.date.fromisoformat(value))
    except ValueError:
        return False


def _get(obj: dict, at: str, key: str, kind: type = str, required: bool = False,
         nonempty: bool = False, date: bool = False) -> Any:
    value = obj.get(key)
    if value is None:
        if required:
            raise ValueError(f"{at}{key}: is required")
        return None
    if not isinstance(value, kind):
        raise ValueError(f"{at}{key}: must be {TYPE_NAMES[kind]}")
    if nonempty and not value.strip():
        raise ValueError(f"{at}{key}: must not be empty")
    if date and not is_date(value):
        raise ValueError(f"{at}{key}: must be a real date written YYYY-MM-DD")
    return value


def _items(obj: dict, key: str, required: bool) -> list[tuple[str, dict, str]]:
    out, seen = [], set()
    for i, item in enumerate(_get(obj, "", key, list, required) or []):
        at = f"{key}[{i}]."
        if not isinstance(item, dict):
            raise ValueError(f"{key}[{i}]: must be an object")
        item_id = _get(item, at, "id", required=True)
        if not ID_RE.fullmatch(item_id):
            raise ValueError(f"{at}id: may use only letters, digits, - and _")
        if item_id in seen:
            raise ValueError(f"{at}id: {item_id!r} is used twice")
        seen.add(item_id)
        out.append((at, item, item_id))
    return out


def parse_review(obj: Any) -> Review:
    if not isinstance(obj, dict):
        raise ValueError("review: must be a JSON object")
    m = _get(obj, "", "meeting", dict, required=True)
    people = _get(m, "meeting.", "people", list) or []
    if not all(isinstance(person, str) for person in people):
        raise ValueError("meeting.people: must be an array of strings")
    meeting = Meeting(
        title=_get(m, "meeting.", "title", required=True, nonempty=True),
        date=_get(m, "meeting.", "date", required=True, date=True),
        people=tuple(people),
        summary=_get(m, "meeting.", "summary", required=True),
        project=_get(m, "meeting.", "project"),
    )
    tasks = tuple(
        Task(
            id=task_id,
            title=_get(t, at, "title", required=True, nonempty=True),
            detail=_get(t, at, "detail") or "",
            project=_get(t, at, "project") if "project" in t else meeting.project,
            due=_get(t, at, "due", date=True),
        )
        for at, t, task_id in _items(obj, "tasks", required=True)
    )
    questions = []
    for at, q, q_id in _items(obj, "questions", required=False):
        options = _get(q, at, "options", list)
        if options is not None and (not options or not all(isinstance(o, str) and o.strip() for o in options)
                                    or len(set(options)) != len(options)):
            raise ValueError(f"{at}options: must be one or more distinct, non-empty strings")
        questions.append(Question(q_id, _get(q, at, "text", required=True, nonempty=True), tuple(options or ())))
    return Review(meeting, tasks, tuple(questions))


def parse_submission(review: Review, pairs: list[tuple[str, str]]) -> dict:
    form: dict[str, str] = {}
    for name, value in pairs:
        form.setdefault(name, value)

    def field(name: str) -> str:
        value = form.get(name, "").replace("\r\n", "\n")
        if len(value) > MAX_TEXT:
            raise ValueError(f"{name}: is longer than {MAX_TEXT} characters")
        return value

    tasks = []
    for task in review.tasks:
        n = f"task.{task.id}"
        if field(f"{n}.keep") not in ("keep", "drop"):
            raise ValueError(f"{n}.keep: must be keep or drop")
        due = field(f"{n}.due") or None
        if due is not None and not is_date(due):
            raise ValueError(f"{n}.due: must be a real date written YYYY-MM-DD")
        tasks.append({"id": task.id, "keep": field(f"{n}.keep") == "keep",
                      "title": " ".join(field(f"{n}.title").split()) or task.title, "due": due,
                      "note": field(f"{n}.note").strip()})
    answers: dict[str, str | None] = {}
    for q in review.questions:
        answers[q.id] = (field(f"q.{q.id}") if q.options else field(f"q.{q.id}").strip()) or None
        if q.options and answers[q.id] is not None and answers[q.id] not in q.options:
            raise ValueError(f"q.{q.id}: must be one of the options")
    return {
        "submitted_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tasks": tasks,
        "answers": answers,
        "notes": field("notes").strip(),
    }


CSS = """
:root{color-scheme:light dark;--bg:#f7f7f4;--fg:#1c1c1a;--muted:#6b6b65;--line:#d9d9d2;--card:#fff;--accent:#2456c4;--on:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#121211;--fg:#ececea;--muted:#9b9b94;--line:#35352f;--card:#1c1c1a;--accent:#7aa2ff;--on:#0d0d0c}}
*{box-sizing:border-box} [hidden]{display:none}
body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.45 -apple-system,system-ui,"Segoe UI",Roboto,sans-serif;-webkit-text-size-adjust:100%}
main{max-width:640px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;line-height:1.2;margin:0 0 6px}
h2{font-size:13px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:32px 0 10px}
p{margin:0 0 12px} ul{padding-left:20px}
.meta,.detail,.empty{color:var(--muted)} .meta{font-size:15px} .summary,.detail{white-space:pre-line}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:10px;margin:0 0 12px}
.card:has(input[value=drop]:checked) .fields{opacity:.4}
.seg{display:grid;grid-template-columns:1fr 1fr;gap:4px;padding:3px;margin:0 0 10px;border:1px solid var(--line);border-radius:11px;background:var(--bg)}
.seg label{position:relative;cursor:pointer} .seg input{position:absolute;opacity:0;pointer-events:none}
.seg span{display:flex;align-items:center;justify-content:center;min-height:46px;border-radius:8px;font-weight:600}
.seg input:checked+span{background:var(--accent);color:var(--on)}
.seg input[value=drop]:checked+span{background:var(--fg);color:var(--bg)}
.seg input:focus-visible+span{outline:2px solid var(--accent);outline-offset:2px}
input[type=date],textarea{display:block;width:100%;min-height:48px;margin:0 0 8px;padding:10px 12px;font:inherit;font-size:17px;color:inherit;background:var(--bg);border:1px solid var(--line);border-radius:10px}
input[type=date]{-webkit-appearance:none;appearance:none} input::-webkit-date-and-time-value{text-align:left}
textarea{resize:vertical} .title{font-weight:600;field-sizing:content}
.row{display:flex;align-items:center;gap:10px} .row span{flex:none;width:2.6em;color:var(--muted)} .row input{margin:0 0 8px}
.tag{display:inline-block;font-size:13px;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:1px 9px}
fieldset{border:0;padding:0;margin:0 0 20px;min-width:0}
legend,.ask span{display:block;padding:0;margin:0 0 8px;font-weight:600} .ask{display:block;margin:0 0 20px}
.opt{display:flex;align-items:center;gap:12px;min-height:50px;padding:0 14px;margin:0 0 6px;border:1px solid var(--line);border-radius:10px;background:var(--card);cursor:pointer}
.opt input{flex:none;width:22px;height:22px;margin:0;accent-color:var(--accent)} .opt span{margin:0;font-weight:400}
button{display:block;width:100%;min-height:56px;margin:28px 0 0;font:inherit;font-size:18px;font-weight:600;color:var(--on);background:var(--accent);border:0;border-radius:12px}
"""


def _day(value: str) -> str:
    day = datetime.date.fromisoformat(value)
    return f"{day:%a, %b} {day.day}"


def _document(title: str, body: str) -> str:
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{esc(title)}</title><style>{CSS}</style></head><body><main>{body}</main></body></html>")


def _task_card(task: Task, meeting_project: str | None) -> str:
    n = f"task.{task.id}"
    detail = f'<p class="detail">{esc(task.detail)}</p>' if task.detail else ""
    tag = f'<p><span class="tag">{esc(task.project or "no project")}</span></p>' if task.project != meeting_project else ""
    return (
        '<div class="card"><div class="seg" role="radiogroup" aria-label="Keep or drop">'
        f'<label><input type="radio" name="{n}.keep" value="keep" checked><span>Keep</span></label>'
        f'<label><input type="radio" name="{n}.keep" value="drop"><span>Drop</span></label></div>'
        f'<div class="fields"><textarea class="title" name="{n}.title" rows="2" aria-label="Title" maxlength="{MAX_TEXT}">'
        f"{esc(task.title)}</textarea>{detail}{tag}"
        f'<label class="row"><span>Due</span><input type="date" name="{n}.due" value="{esc(task.due or "")}"></label>'
        f'<textarea name="{n}.note" rows="2" placeholder="Note" aria-label="Note" maxlength="{MAX_TEXT}"></textarea>'
        "</div></div>"
    )


def _question(q: Question) -> str:
    if not q.options:
        return (f'<label class="ask"><span>{esc(q.text)}</span>'
                f'<textarea name="q.{q.id}" rows="2" maxlength="{MAX_TEXT}"></textarea></label>')
    options = "".join(f'<label class="opt"><input type="radio" name="q.{q.id}" value="{esc(o)}"><span>{esc(o)}</span>'
                      "</label>" for o in q.options)
    return f"<fieldset><legend>{esc(q.text)}</legend>{options}</fieldset>"


def render_form(review: Review) -> str:
    m = review.meeting
    meta = " · ".join(part for part in (_day(m.date), ", ".join(m.people), m.project or "") if part)
    parts = [
        f'<h1>{esc(m.title)}</h1><p class="meta">{esc(meta)}</p><p class="summary">{esc(m.summary)}</p>',
        # A disabled first submit button stops Enter in a date field from sending this one-shot form.
        # Safari honors it. Chrome still submits on Enter in a date field, and no-JS can't stop that.
        '<form method="post"><button type="submit" disabled hidden aria-hidden="true"></button>',
    ]
    if review.tasks:
        parts += ["<h2>Tasks</h2>", *(_task_card(task, m.project) for task in review.tasks)]
    else:
        parts.append('<p class="empty">No tasks came out of this meeting.</p>')
    if review.questions:
        parts += ["<h2>Questions</h2>", *(_question(q) for q in review.questions)]
    parts.append(f'<label class="ask"><span>Anything else?</span><textarea name="notes" rows="3" maxlength="{MAX_TEXT}">'
                 '</textarea></label><button type="submit">Send</button></form>')
    return _document(m.title, "".join(parts))


def render_sent(review: Review, response: dict) -> str:
    kept = [t for t in response["tasks"] if t["keep"]]
    parts = [f'<h1>Sent.</h1><p class="meta">{esc(review.meeting.title)}</p>',
             f"<p>{len(kept)} kept · {len(response['tasks']) - len(kept)} dropped</p>"]
    if kept:
        items = "".join(f"<li>{esc(t['title'])}" + (f' <span class="meta">· due {_day(t["due"])}</span>' if t["due"] else "")
                        + "</li>" for t in kept)
        parts.append(f"<h2>Kept</h2><ul>{items}</ul>")
    if review.questions:
        parts.append("<h2>Answers</h2>")
        parts += [f'<p class="ask"><span>{esc(q.text)}</span>{esc(response["answers"].get(q.id) or "No answer")}</p>'
                  for q in review.questions]
    return _document(f"Sent · {review.meeting.title}", "".join(parts))


def render_error(title: str, message: str) -> str:
    return _document(title, f"<h1>{esc(title)}</h1><p>{esc(message)}</p>")


@dataclass(frozen=True)
class Store:
    root: Path

    def create(self, raw: bytes) -> str:
        slug = secrets.token_urlsafe(16)
        while slug.startswith("-"):  # `show -abc` would parse as an option
            slug = secrets.token_urlsafe(16)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        folder = self.root / slug
        folder.mkdir(mode=0o700)
        (folder / "review.json.tmp").write_bytes(raw)
        os.replace(folder / "review.json.tmp", folder / "review.json")
        return slug

    def read(self, slug: str) -> tuple[Any, Any] | None:
        folder = self.root / slug
        if not SLUG_RE.fullmatch(slug) or not (folder / "review.json").is_file():
            return None
        response = folder / "response.json"
        return (json.loads((folder / "review.json").read_bytes()),
                json.loads(response.read_bytes()) if response.exists() else None)

    def respond(self, slug: str, response: dict) -> bool:
        tmp = self.root / slug / f"response.{secrets.token_hex(8)}.tmp"
        tmp.write_bytes(json.dumps(response, indent=2).encode() + b"\n")
        try:
            # link() refuses an existing target, so exactly one concurrent submit wins. Unlike an
            # O_EXCL create followed by a write, no reader ever sees an empty response.json.
            os.link(tmp, self.root / slug / "response.json")
            return True
        except FileExistsError:
            return False
        finally:
            tmp.unlink()

    def delete(self, slug: str) -> None:
        shutil.rmtree(self.root / slug, ignore_errors=True)


def default_store() -> Store:
    return Store(Path(os.environ.get("REVIEW_FORM_DATA") or "~/.review-form").expanduser())


class Handler(BaseHTTPRequestHandler):
    server: Server
    server_version = "review-form"
    sys_version = ""

    def end_headers(self) -> None:
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        super().end_headers()

    def _page(self, status: int, body: str, location: str = "") -> None:
        data = body.encode()
        self.send_response(status)
        if location:
            self.send_header("Location", location)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _error(self, status: int, title: str, message: str) -> None:
        self._page(status, render_error(title, message))

    def _find(self) -> tuple[str, Review, Any] | None:
        slug = urllib.parse.urlsplit(self.path).path.rstrip("/").rsplit("/", 1)[-1]
        found = self.server.store.read(slug)
        return None if found is None else (slug, parse_review(found[0]), found[1])

    def do_GET(self) -> None:
        found = self._find()
        if found is None:
            return self._error(404, "Not found", "There is no review at this link.")
        _, review, response = found
        self._page(200, render_form(review) if response is None else render_sent(review, response))

    do_HEAD = do_GET

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length > MAX_BODY:
            return self._error(413, "Too large", "The form was too large to send.")
        if length < 0:
            return self._error(400, "Not sent", "The request had a bad Content-Length.")
        body = self.rfile.read(length)
        found = self._find()
        if found is None:
            return self._error(404, "Not found", "There is no review at this link.")
        slug, review, response = found
        origin = urllib.parse.urlsplit(self.headers.get("Origin", "")).netloc.lower()
        if not origin or origin != self.headers.get("Host", "").lower():
            return self._error(403, "Not sent", "The form has to be sent from its own page.")
        if self.headers.get_content_type() != "application/x-www-form-urlencoded":
            return self._error(415, "Not sent", "The form must be sent as application/x-www-form-urlencoded.")
        if response is not None:
            return self._error(409, "Already sent", ALREADY_SENT)
        try:
            submission = parse_submission(review, urllib.parse.parse_qsl(body.decode("utf-8", "replace"),
                                                                         keep_blank_values=True))
        except ValueError as e:
            return self._error(400, "Not sent", f"{e}. Go back, fix it, and send again.")
        if not self.server.store.respond(slug, submission):
            return self._error(409, "Already sent", ALREADY_SENT)
        # Relative, so the browser keeps the path prefix that tailscale serve strips before proxying.
        self._page(303, "", location=slug)


class Server(ThreadingHTTPServer):
    def __init__(self, host: str, port: int, store: Store) -> None:
        self.address_family = socket.AF_INET6 if ipaddress.ip_address(host).version == 6 else socket.AF_INET
        self.store = store
        super().__init__((host, port), Handler)


def serve(host: str, port: int) -> int:
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        print(f"review_form: refusing to listen on {host}. Use a loopback address such as 127.0.0.1 "
              "and reach it through tailscale serve.", file=sys.stderr)
        return 2
    store = default_store()
    server = Server(host, port, store)
    print(f"review_form: listening on http://{host}:{server.server_address[1]} with data in {store.root}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def publish(path: str) -> int:
    base = os.environ.get("REVIEW_FORM_BASE_URL", "").rstrip("/")
    if not base:
        print("review_form: set REVIEW_FORM_BASE_URL to the URL your phone opens, without the slug.", file=sys.stderr)
        return 1
    try:
        raw = Path(path).read_bytes()
        parse_review(json.loads(raw))
    except (OSError, ValueError) as e:
        print(f"review_form: {path}: {e}", file=sys.stderr)
        return 1
    store = default_store()
    slug = store.create(raw)
    url = f"{base}/{slug}"
    # A tailnet URL never goes through an HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    problem = ""
    for attempt in range(3):
        if attempt:
            time.sleep(1)
        try:
            with opener.open(url, timeout=10) as r:
                if r.status == 200:
                    print(url)
                    return 0
                problem = f"HTTP {r.status}"
        except urllib.error.HTTPError as e:
            problem = f"HTTP {e.code}"
        except OSError as e:
            problem = str(getattr(e, "reason", e))
    store.delete(slug)
    print(f"review_form: {url} did not open ({problem}), so the review was not kept. Is `review_form.py serve` "
          "running with the same REVIEW_FORM_DATA? Check `tailscale serve status`.", file=sys.stderr)
    return 1


def show(slug: str) -> int:
    store = default_store()
    found = store.read(slug)
    if found is None:
        print(f"review_form: no review {slug!r} in {store.root}", file=sys.stderr)
        return 1
    base = os.environ.get("REVIEW_FORM_BASE_URL", "").rstrip("/")
    print(json.dumps({"slug": slug, "url": f"{base}/{slug}" if base else None,
                      "review": found[0], "response": found[1]}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="review_form.py", description="Meeting review forms for your phone.")
    commands = parser.add_subparsers(dest="command", required=True)
    serve_cmd = commands.add_parser("serve", help="serve every published review")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=os.environ.get("REVIEW_FORM_PORT") or "8787")
    commands.add_parser("publish", help="validate, save, and check a review file").add_argument("file")
    commands.add_parser("show", help="print a review and its response as JSON").add_argument("slug")
    args = parser.parse_args(argv)
    if args.command == "serve":
        return serve(args.host, args.port)
    return publish(args.file) if args.command == "publish" else show(args.slug)


if __name__ == "__main__":
    sys.exit(main())
