# Set up automatic meeting processing for me

Paste this whole file into your agent (Claude Code, Codex, Hermes, Cursor,
whatever you run). Nothing to fill in. The agent interviews you about your
setup first, then builds the pipeline with your tools. The process is the
part that matters, not the tools.

---

I want you to build me an automatic meeting-processing pipeline. Read all of
this before you touch anything. Then interview me, one question at a time,
and build only after I have answered everything in the last section.

## What you are adapting to

The process below is written against one setup: Granola records the meeting,
an Obsidian vault holds the notes, TaskNotes holds the tasks, a Discord
thread is where I get asked. Swap every one of those for what I tell you in
the interview. If I do not take meeting notes at all yet, help me pick a
recorder first, then continue.

## The rules. Break one and the run is a failure.

1. **The recorder is read-only to you.** You never edit, rename, or delete a
   recording, transcript, or AI summary at the source.
2. **My words stay mine.** You file, format, link, and summarize. You never
   write a commitment, decision, or note I did not say.
3. **Nothing becomes a task without my yes.** You list what I committed to
   and ask. My reply is what creates the task. Silence creates nothing.
4. **A question gets asked, never guessed.** Which client, which project, which
   due date, who this new person is. If you are not sure, it goes on the
   question list.
5. **Every write leaves a receipt.** A commit where the target is a git repo,
   a log line in my notes where it is not. No silent writes.
6. **The run is not done until the gate says so.** The last step checks that
   every earlier step left evidence. It refuses when one is missing, and you
   go back and do that step. You never report a meeting as processed on your
   own word.

## Per meeting, in this order

1. **Detect.** Watch the recorder for a meeting whose transcript and summary
   are finished. A meeting still running is never pulled. Keep a list of
   processed meeting ids so a double trigger is a no-op. Prefer a webhook
   from the recorder. Fall back to a poll every 10 minutes.

2. **Pull** the full transcript, the recorder's summary, the calendar event
   (title, start, attendees, their emails), and my own typed notes if the
   recorder has them.

3. **Find or create the meeting note** in my notes system. Match on the
   calendar event id first. Name new notes `YYYY-MM-DD HHMM <Topic>` from the
   meeting's local start time. Use my meeting template if one exists. Never
   invent fields the template does not have.

4. **File into the note, these sections, this order, nothing else:**
   - `Summary`: one or two lines.
   - `Decisions`: what was decided, one line each.
   - `Action items`: empty until I reply. It shows the tasks my yes creates.
     Never a task typed inline.
   - `Notes`: my typed notes first, then the recorder's notes, including what
     other people committed to.
   - `Transcript`: link to the source on the first line, then the full text.

5. **Client meeting?** If an attendee's email domain or name maps to one of my
   client folders, also write a copy of the transcript and notes to that
   folder under `meetings/YYYY-MM-DD-HHMM-<topic>`. Leave my action items out
   of the client copy. Link the two files to each other. If you are unsure
   which client, write no copy and put it on the question list.

6. **Link.** Each attendee to their contact page, and update their
   last-contact date. The project, when one is clearly named. A new person
   gets a contact page from my people template, and their organization when
   the email domain makes it obvious. My own identities are never attendees
   and never become contact pages: `<my emails and domains>`.

7. **Ask me, in one thread, in my chat tool.** Open one new thread titled
   `<date> <topic>`. The body is exactly two numbered lists:
   - My commitments from the call, one line each, my words, with the project
     you think each belongs to.
   - Questions only I can answer: routing, identity, project, due date.
   End with: "Reply here: yes/no per number, and answers. I file the yeses as
   tasks." One thread per meeting. Never a plain message, never a DM.

8. **File only the yeses.** Each yes becomes one task in my task system: the
   commitment verbatim as the title, linked to the meeting and the project,
   due date only if I gave one. A no creates nothing. Reply in the thread
   with links to what you created.

9. **Reconcile the project.** Compare the meeting with the project's current
   plan and open tasks. Record one of `updated`, `no-change`, `pending` with a
   one-line reason. A meeting being filed does not prove the plan is current.

10. **Receipt, then gate.** Commit each repo you touched with the message
    `meeting: <date> <topic>`. Write one log line in my notes for the vault
    writes. Then run the gate: it checks the note exists with the right
    sections and status, the thread exists, the client copy exists when the
    meeting is a client meeting, and the log line exists. Only when it prints
    `processed: true` is the meeting done. Then list again. The run ends when
    the list is empty.

## Build it as

- One deterministic script that lists, pulls, and marks (the gate). No LLM in
  it. It is the source of truth for what is processed.
- One skill or prompt file (this document, adapted) that you run once per
  listed meeting, oldest first.
- A calendar sync that pre-creates the meeting note and contact pages before
  the meeting, so filing appends to a note that already exists.
- Tests for the gate: it must refuse when any piece of evidence is missing.

## Interview me before you build

One question per message. Wait for the answer. Look at my machine and my
accounts before you ask, so the questions are about what you found there.

1. How do meetings get recorded today, if at all? Which recorder, and does it
   have a webhook or an API you can poll?
2. Where should every meeting be filed? Which notes system, and where in it?
3. Where do my tasks live? Which task system, and how does it link a task to
   a note?
4. Where do you reach me with questions, and is a thread possible there?
5. Do I have client work folders? Which ones, and how do you map an attendee
   to one?
6. What are my own emails and domains, so you never file me as an attendee?
7. Do I already have a meeting template and a task schema? Show me what you
   found before you write to either.

Then say back the whole pipeline with my tools in it, in ten lines, and wait
for my yes before you build anything.
