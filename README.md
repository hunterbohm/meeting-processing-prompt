# Automatic meeting processing, the process not the tools

When a meeting ends, I can walk away from my desk. My agent texts me: I got your meeting, these are the things I think you should do, do you want me to add them? If there is any ambiguity about who it was with or what project it belongs to, I clear it up then and there, on the walk. Nothing becomes a task until I say yes.

Mine runs on Granola, an Obsidian vault, TaskNotes, a Hermes agent on a Mac mini, and a Discord thread. Yours does not have to. The process is the part that matters.

This repo gives you one file.

| File | What it is |
|---|---|
| [`SETUP-PROMPT.md`](SETUP-PROMPT.md) | Paste it into your agent. It interviews you about how you record meetings, where your notes and tasks live, and where it can reach you. Then it builds the same pipeline with your tools. |

## The one rule, if you only keep one

Nothing becomes a task without my reply. The agent lists what I committed to and asks. My yes creates the task. Silence creates nothing.

## Set it up

1. Open your agent (Claude Code, Codex, Hermes, Cursor, whatever you run) on the machine that will do the work.
2. Paste the whole of `SETUP-PROMPT.md`.
3. Answer its questions one at a time. It looks at your setup first, so the questions are about what it found.
4. It says the pipeline back to you with your tools in it. Say yes only when that is the pipeline you want.

If you do not record meetings at all yet, say so. It helps you pick a recorder first.

## What the six rules are for

1. The recorder is read-only to the agent.
2. My words stay mine. The agent files, formats, links, summarizes. It authors nothing.
3. Nothing becomes a task without my yes.
4. A question gets asked, never guessed.
5. Every write leaves a receipt. A commit, or a log line.
6. The run is not done until the gate says so. A plain script, no model in it, checks that every step left its file behind. If one is missing it refuses, names the step, and the meeting stays in the queue.

Every one of these exists because an agent did the opposite. Tasks that were meant for somebody else. Commitments I never made. The night it wrote the note, stopped halfway, and told me the meeting was processed. Rule six was written at one in the morning after that one.
