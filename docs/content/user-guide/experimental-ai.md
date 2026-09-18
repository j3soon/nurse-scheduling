# Experimental AI Chat

[Open Experimental AI](https://nursescheduling.org/experimental-ai){ .md-button .md-button--primary }

!!! warning "Experimental"
    AI answers may be incorrect. Verify them against the schedule before use.

The hosted assistant is an API-key-gated beta. See
[AI Beta Access](https://github.com/j3soon/nurse-scheduling#ai-beta-access)
to request access.

This page answers questions about the schedule currently open in the browser.
A question can include files of any type when **Attach files** is available.
The assistant can inspect common text, image, PDF, and spreadsheet formats in
its temporary workspace. The assistant can propose changes to the schedule,
which apply only after you approve them. It cannot run optimization.

## Review a proposed change

Ask for a change, such as renaming a person or adding a shift request, and the
assistant proposes one instead of changing the schedule itself.

1. Ask for the change in the usual way.
2. Read **Proposed schedule change**, which lists every difference between your
   current schedule and the proposal.
3. Select **Approve** to apply it, or **Reject** to discard it.
4. An approved proposal replaces the schedule in one step, so
   <kbd>Ctrl</kbd>+<kbd>Z</kbd> reverts the whole change.

## See what the assistant did

Small grey rows under an answer record how it was produced. They stay collapsed
until you select one.

- **Reasoning** shows the model's own thinking for that step.
- The `bash` tool shows the command the assistant ran and its bounded output.
  The assistant may read task-sized schedule references from the temporary
  sandbox when it needs schema guidance.
- **schedule edit** shows the changed lines after a Bash command changes the
  temporary schedule. Red lines were removed and green lines were added. This
  is a preview only. The current schedule still changes only after you approve
  the final proposal.
- A row marked `failed` means that step changed nothing. This is the usual
  reason an answer arrives without a proposal.

Long output is revealed a portion at a time with **Show more**. Clear
**Show reasoning** or **Show tool activity** near the top of the page to hide
either kind. The choice is remembered on this browser.

Approval is refused when the schedule changed after the proposal was made. Ask
again so the assistant works from what you now have.

## Real scenario example

For the anonymized 87-person ward example, load
`large-ward-with-87-people-2025-11.yaml`, then open **Experimental AI**. Confirm
that the snapshot shows 87 people and 30 dates before asking a question.

![Experimental AI chat with the 87-person schedule loaded](../assets/images/user-guide/21-real-experimental-ai.png)

The blue development-version banner appears only in non-release builds.

## Ask about a schedule

1. Finish editing or load the intended schedule.
2. Open **Experimental AI**.
3. Confirm the displayed people and date counts.
4. If **Attach files** is available, optionally select files and confirm the
   displayed names. Remove an incorrect file with its **×** button.
5. Enter a question and select **Send**. Press <kbd>Enter</kbd> to send or
   <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line. Where browser speech
   recognition is available, select the microphone to dictate the question.
6. While the assistant is working, enter another message and select **Queue**
   to steer the same turn after its next tool call. This does not cancel work
   already in progress.
7. Select **Stop** to interrupt a response in progress.
8. If you scroll up in a long conversation, use the floating down-arrow button
   to return to the composer and latest message.

The animated **Thinking** indicator means the assistant is waiting for its
first response text.

Assistant answers render Markdown, including headings, lists, links, code, and
tables. Use the copy icon at the top-right of a code block to copy its contents.
Raw HTML is ignored. Remote images written in an answer are not loaded.
Use **HTML** under **Export chat** for a styled, standalone transcript, or
**Markdown** for a plain-text transcript. Export runs in the browser.

## Ask how to use the app

The assistant runs inside the existing Nurse Scheduling app and can explain
which page and visible control to use for a task. For example, ask how to add a
person, upload schedule YAML, configure a rule, or start optimization. It can
guide you through those controls, but it cannot navigate, click, upload, or run
optimization for you.

Files attached with **Attach files** belong to the next chat message. To replace
the schedule currently open in the app, use **Upload** on **Save and Load**
instead.

The browser uploads one YAML snapshot when it creates the chat session. Later
questions in that session use the same service-held snapshot. The current
browser tab preserves the transcript when you switch pages or reload. A chat
expires after 48 hours without a message. Each new message renews that period,
and the page reports when a preserved chat has expired.

## Data and limitations

The complete schedule YAML is sent to the configured AI service and placed in
the assistant's temporary workspace. Relevant schedule content reaches the
model when the assistant inspects it. Attached files are copied to that isolated
workspace for the current question and are destroyed with it. The assistant can
inspect spreadsheet cells, including formulas and last-saved values, or extract
text and render selected PDF pages. Rendered pages and any images the assistant
extracts may be sent to the model when it reads them. File support still depends
on the inspection tools installed in the workspace, and the assistant does not
execute attachments.

AI chats and related data may be logged, retained, and processed for the
development, evaluation, and improvement of this product and the AI provider's
products. The AI service does not currently anonymize schedules, chats, or
attachments. Do not submit personal, confidential, regulated, or otherwise
sensitive information. See the
[privacy policy](https://github.com/j3soon/nurse-scheduling/blob/dev/PRIVACY.md)
for details.

Chat sessions use unguessable identifiers but do not have account
authentication yet. Model answers may be incorrect, so verify them against the
schedule.
