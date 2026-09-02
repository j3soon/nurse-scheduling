# Experimental AI Chat

[Open Experimental AI](https://nursescheduling.org/experimental-ai){ .md-button .md-button--primary }

!!! warning "Experimental"
    AI answers may be incorrect. Verify them against the schedule before use.

This page answers questions about the schedule currently open in the browser.
When enabled by the AI backend, a question can include PNG, JPEG, and WebP
images or TXT, Markdown, CSV, PDF, and XLSX documents. The assistant can propose
changes to the schedule, which apply only after you approve them. It cannot run
optimization.

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
  The assistant may invoke the `nsctl` schema helper from Bash.
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
4. If **Attach files** is available, optionally select supported images or
   documents and confirm the displayed files. Remove an incorrect file with
   its **×** button.
5. Enter a question and select **Send**. Press <kbd>Enter</kbd> to send or
   <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line.
6. Select **Stop** to cancel a response in progress.
7. If you scroll up in a long conversation, use the floating down-arrow button
   to return to the composer and latest message.

The animated **Thinking** indicator means the assistant is waiting for its
first response text.

Assistant answers render Markdown, including headings, lists, links, code, and
tables. Use the copy icon at the top-right of a code block to copy its contents.
Raw HTML is ignored. Remote images written in an answer are not loaded.

The browser uploads one YAML snapshot when it creates the chat session. Later
questions in that session use the same backend-owned snapshot. Reload the page
to begin a new chat from the latest schedule.

## Data and limitations

The complete schedule YAML is sent to the configured AI backend and model
provider. Attached images are also sent to that provider for the current
question, as are the extracted contents and filenames of attached documents.
PDF extraction reads embedded text and does not perform OCR. XLSX extraction
includes cell values, formula text, and cached formula results when available.
It does not recalculate formulas. Attachment contents are not retained in
backend chat history. Document filenames remain as history markers. People
IDs, descriptions, rules, dates, images, and documents may be sensitive. Use
only an approved provider and anonymize sensitive data first when required.

Chat sessions use unguessable identifiers but do not have account
authentication yet. Sessions are stored in AI-backend memory and disappear
when that process restarts. Model answers may be incorrect, so verify them
against the schedule.
