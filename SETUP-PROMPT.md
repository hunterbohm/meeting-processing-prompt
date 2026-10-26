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

The process below is written against one setup. A recorder transcribes every
call. An Obsidian vault holds the notes, and TaskNotes holds the tasks. A Mac
mini that is always on does the work. After each meeting, the mini publishes a
review form and texts me its link over iMessage. The form opens only on my
private Tailscale network. Swap every one of those for what I tell you in the
interview. If I do not record meetings at all yet, help me pick a recorder
first, then continue.

The review form is in the repo this prompt comes from:
https://github.com/hunterbohm/meeting-processing-prompt, folder
`review-form/`. It is one Python file with no dependencies. Read its README.
Use it unless I already have a way to publish a private form.

## The rules. Break one and the run is a failure.

1. **The recorder is read-only to you.** You never edit, rename, or delete a
   recording, transcript, or AI summary at the source.
2. **My words stay mine.** You file, format, link, and summarize. You never
   write a commitment, decision, or note I did not say.
3. **Nothing becomes a task without my yes.** You put what I committed to in
   the review form. When I submit it, each task I left on keep is a yes. A
   task I drop creates nothing. A form I never submit creates nothing.
4. **A question gets asked, never guessed.** Which client, which project, which
   due date, who this new person is. If you are not sure, it goes in the
   form's questions.
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
   - `Action items`: empty until I submit the review. It shows the tasks my
     keeps create. Never a task typed inline.
   - `Notes`: my typed notes first, then the recorder's notes, including what
     other people committed to.
   - `Transcript`: link to the source on the first line, then the full text.

5. **Client meeting?** If an attendee's email domain or name maps to one of my
   client folders, also write a copy of the transcript and notes to that
   folder under `meetings/YYYY-MM-DD-HHMM-<topic>`. Leave my action items out
   of the client copy. Link the two files to each other. If you are unsure
   which client, write no copy and put it in the form's questions.

6. **Link.** Each attendee to their contact page, and update their
   last-contact date. The project, when one is clearly named. A new person
   gets a contact page from my people template, and their organization when
   the email domain makes it obvious. My own identities are never attendees
   and never become contact pages: `<my emails and domains>`.

7. **Ask me with one review form, texted to my phone.** Write one review file
   for the meeting with three parts:
   - The meeting: title, date, people, a one or two line summary, the
     project, and the path of the meeting note.
   - My commitments from the call, one task each, in my words. Give each the
     project you think it belongs to. Give a due date only if I said one.
   - Questions only I can answer: routing, identity, project, due date. When
     the answer is one of a few, list the options.

   Publish it with `review_form.py publish`. It prints the link only after the
   link opens. Then text me two short messages: `meeting with <first name> is
   done, review when you have time`, then the link alone. Save the meeting id,
   the review slug, and the send result as delivery evidence.

   The link opens only on my devices. Serve the form on my private network
   with Tailscale Serve, never Tailscale Funnel or any other public URL. The
   page holds my meeting summary and my commitments.

   One review per meeting. Before you publish, check the saved slug. If the
   meeting already has a review, publish no second one. If the text failed,
   send the same link again. If you cannot tell whether the text went out,
   report the review as pending rather than sending again. Never paste the
   review into a long message in place of the link.

8. **File only the kept tasks.** A small script with no model in it runs
   every 10 minutes. For each review I submitted that it has not applied yet,
   it creates one task per kept card. The title is my edited title, verbatim.
   The task links to the meeting and the project. It gets my due date only if
   I set one, and my card note goes in the task body. A dropped card creates
   nothing. Then the script marks the review applied and texts me one line:
   `<meeting>: filed 3 tasks, dropped 1`. A second run files nothing new.

   My answers to the questions and my "anything else" note are not applied
   by the script. It puts them in its text, and you apply them next: move a
   task to the project I named, fix a contact, set the date. If an answer is
   unclear, ask me again. Do not guess.

9. **Reconcile the project.** Compare the meeting with the project's current
   plan and open tasks. Record one of `updated`, `no-change`, `pending` with a
   one-line reason. A meeting being filed does not prove the plan is current.

10. **Draft a follow-up, for outside meetings only.** After a one-off meeting
    with someone outside my work, such as a sales or discovery call, draft a
    follow-up email in my voice: thanks, what we decided, and who owes what
    by when. Use only what is in the filed note. Save it as a draft in my
    email. Never send it. I send it myself. Recurring syncs and internal calls
    get no draft.

11. **Receipt, then gate.** Commit each repo you touched with the message
    `meeting: <date> <topic>`. Write one log line in my notes for the vault
    writes. Then run the gate. It checks that the note exists with the right
    sections and status, that the review link opens and its text was sent,
    that the client copy exists when the meeting is a client meeting, and
    that the log line exists. Only when it prints `processed: true` is the
    meeting done. Then list again. The run ends when the list is empty.

## Build it as

- One deterministic script that lists, pulls, and marks (the gate). No LLM in
  it. It is the source of truth for what is processed.
- One skill or prompt file (this document, adapted) that you run once per
  listed meeting, oldest first.
- A calendar sync that pre-creates the meeting note and contact pages before
  the meeting, so filing appends to a note that already exists.
- The review form from `review-form/`, running on the always-on machine as a
  service that restarts after a reboot: launchd on a Mac, systemd on Linux.
  Serve it on my tailnet with `tailscale serve`. My phone needs Tailscale too.
- The apply script from step 8, on a 10-minute schedule.
- A weekly check for missed meetings: calendar meetings from the last 14 days
  with nothing filed. Ask me about each. If it happened, file what I tell you
  and say in the transcript section that it was not recorded. If it did not
  happen, record that and never ask about it again.
- Tests for delivery, the apply script, and the gate:
  - The gate refuses a meeting whose review was not published or whose text
    was not sent.
  - A duplicate trigger reuses the saved review and publishes no second one.
  - The apply script files only kept cards, uses my edited titles, and files
    nothing on a second run.
  - A review with no submission files nothing.
- Before calling the setup ready, run one real meeting, with my okay, through
  the trigger, the filing, the text, and the gate. I open the link on my
  phone, drop one task, edit another, and submit. Confirm that the kept tasks
  appear in my task system and the dropped one does not. Keep simulated tests
  distinct from this live check.

## Interview me before you build

One question per message. Wait for the answer. Look at my machine and my
accounts before you ask, so the questions are about what you found there.

1. How do meetings get recorded today, if at all? Which recorder, and does it
   have a webhook or an API you can poll?
2. Where should every meeting be filed? Which notes system, and where in it?
3. Where do my tasks live? Which task system, and how does it link a task to
   a note?
4. Which machine is always on? The form and the schedules run there. Is
   Tailscale on it and on my phone? If not, set it up with me now.
5. How do you text me? iMessage from a Mac, Telegram, Signal, SMS, or a
   direct message in a chat app. Send one test message and wait for me to
   confirm it arrived.
6. Do I have client work folders? Which ones, and how do you map an attendee
   to one?
7. What are my own emails and domains, so you never file me as an attendee?
8. Do I already have a meeting template and a task schema? Show me what you
   found before you write to either.
9. Which email account holds follow-up drafts, if I want them?

Then say back the whole pipeline with my tools in it, in ten lines, and wait
for my yes before you build anything.
