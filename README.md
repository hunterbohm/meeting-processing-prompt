# Automatic meeting processing, the process not the tools

When a meeting ends, I can walk away from my desk. My agent texts me a link. On my phone I see a short summary, the tasks it thinks I committed to, and anything it could not work out on its own, like which project a task belongs to. I keep or drop each task, fix a title, set a date, answer the questions, and submit. Nothing becomes a task until I do.

Mine runs on a recorder I built that transcribes every call, an Obsidian vault, TaskNotes, and a Hermes agent on a Mac mini that texts me over iMessage. The form lives on the mini and opens only on my Tailscale network, so my meeting notes never sit on a public page. Yours does not have to use any of these. The process is the part that matters.

This repo gives you two things.

| File | What it is |
|---|---|
| [`SETUP-PROMPT.md`](SETUP-PROMPT.md) | Paste it into your agent. It interviews you about how you record meetings, where your notes and tasks live, and how it can text you. Then it builds the same pipeline with your tools. |
| [`review-form/`](review-form/) | The review form. One Python file with no dependencies. Your agent runs it on your always-on machine and serves it on your Tailscale network. |

## The one rule, if you only keep one

Nothing becomes a task without my yes. The agent puts what I committed to in the form. Each task I keep is a yes. Silence creates nothing.

## Set it up

Watch the walkthrough: [I Automated My Meeting Follow-Up with Hermes](https://www.youtube.com/watch?v=c4MT2CAtMkA). The video shows the first version, which asked me in a Discord thread. It now asks with the form.

1. Open your agent (Claude Code, Codex, Hermes, Cursor, whatever you run) on the machine that will do the work. Pick one that stays on.
2. Paste the whole of `SETUP-PROMPT.md`.
3. Answer its questions one at a time. It looks at your setup first, so the questions are about what it found.
4. It says the pipeline back to you with your tools in it. Say yes only when that is the pipeline you want.

If you do not record meetings at all yet, say so. It helps you pick a recorder first. If you do not have Tailscale yet, it sets that up with you too.

## What the six rules are for

1. The recorder is read-only to the agent.
2. My words stay mine. The agent files, formats, links, summarizes. It authors nothing.
3. Nothing becomes a task without my yes.
4. A question gets asked, never guessed.
5. Every write leaves a receipt. A commit, or a log line.
6. The run is not done until the gate says so. A plain script, no model in it, checks the files, checks that the review link opens, and checks that the text went out. If evidence is missing it refuses, names the step, and the meeting stays in the queue.

Every one of these exists because an agent did the opposite. Tasks that were meant for somebody else. Commitments I never made. The night it wrote the note, stopped halfway, and told me the meeting was processed. Rule six was written at one in the morning after that one.
