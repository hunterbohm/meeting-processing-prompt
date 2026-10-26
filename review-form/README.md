# review-form

*AI-generated README.*

A one-file web form for reviewing a meeting on your phone. Your agent
publishes one review per meeting. You keep or drop each task, edit its title,
due date, and note, answer the questions, and submit once. Your scripts read
the result back as JSON.

It needs Python 3.9 or later and no packages.

## Run it on your tailnet

On the machine that is always on:

```sh
python3 review_form.py serve
tailscale serve --bg --set-path /review http://127.0.0.1:8787
export REVIEW_FORM_BASE_URL=https://<machine>.<tailnet>.ts.net/review
```

`tailscale serve` makes the form reachable over HTTPS from devices on your
tailnet only. Do not use `tailscale funnel`. Funnel puts the form on the
public internet.

Run `serve` as a service so it comes back after a reboot: a launchd agent on a
Mac, a systemd unit on Linux. Give the service the same environment
variables.

## Commands

| Command | What it does |
|---|---|
| `review_form.py serve [--port P]` | Serves every published review. It listens on `127.0.0.1` and refuses any address that is not loopback. |
| `review_form.py publish <review.json>` | Validates the review file, saves it, and checks that its link opens. Prints the link on success. Prints nothing to stdout and exits 1 when the file is invalid or the link does not return 200. |
| `review_form.py show <slug>` | Prints the review and its response as one JSON object. `response` is `null` until you submit. |

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `REVIEW_FORM_BASE_URL` | none, required by `publish` | The URL your phone opens, without the slug. |
| `REVIEW_FORM_DATA` | `~/.review-form` | Where reviews and responses are saved. |
| `REVIEW_FORM_PORT` | `8787` | The port `serve` listens on. |

## The review file

[`example-review.json`](example-review.json) is a full example.

```json
{
  "meeting": {
    "title": "Weekly sync with Dana",
    "date": "2026-10-26",
    "people": ["Dana Lee"],
    "summary": "Scope is final. Launch moves to November 12.",
    "project": "Website rebuild",
    "note": "Meetings/2026-10-26 1500 Weekly sync with Dana.md"
  },
  "tasks": [
    {
      "id": "1",
      "title": "Send Dana the revised scope",
      "detail": "She needs it before Friday's call.",
      "project": "Website rebuild",
      "due": "2026-10-30"
    }
  ],
  "questions": [
    {
      "id": "q1",
      "text": "Is the logo work part of Website rebuild or a new project?",
      "options": ["Website rebuild", "New project"]
    }
  ]
}
```

`meeting.title`, `meeting.date`, `meeting.summary`, and `tasks` are required.
Each task needs an `id` and a `title`. Each question needs an `id` and a
`text`. Ids use letters, digits, `-`, and `_`, and are unique within their
list. Dates are `YYYY-MM-DD`. The form ignores keys it does not know, and
`show` returns the file as you published it, so you can keep your own fields
in it, such as `meeting.note`.

## The response

You can submit each review once. A second submit is refused, so your apply
script never sees two answers for one meeting.

```json
{
  "submitted_at": "2026-10-26T20:14:03Z",
  "tasks": [
    {"id": "1", "keep": true, "title": "Send Dana the revised scope", "due": "2026-10-30", "note": ""}
  ],
  "answers": {"q1": "New project"},
  "notes": ""
}
```

`tasks` has one entry per task, in the review's order. `title` is the title as
you left it, with runs of spaces and line breaks made single spaces. If you
cleared the title, it is the original. `due` is `null` when you cleared it.
`answers` has every question id, with `null` for a question you left blank.
`notes` is the "anything else" box.

## Test it

```sh
python3 -m unittest -v
```
