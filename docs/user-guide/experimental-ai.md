# Experimental AI Chat

[Open Experimental AI](https://nursescheduling.org/experimental-ai){ .md-button .md-button--primary }

!!! warning "Experimental"
    AI answers may be incorrect. Verify them against the schedule before use.

This page answers text questions about the schedule currently open in the
browser. It cannot change the schedule, attach files, or run optimization.

## Real scenario example

For the anonymized 87-person ward example, load
`large-ward-with-87-people-2025-11.yaml`, then open **Experimental AI**. Confirm
that the snapshot shows 87 people and 30 dates before asking a question.

![Experimental AI chat with the 87-person schedule loaded](../assets/images/user-guide/21-real-experimental-ai.png)

## Ask about a schedule

1. Finish editing or load the intended schedule.
2. Open **Experimental AI**.
3. Confirm the displayed people and date counts.
4. Enter a question and select **Send**. Press <kbd>Enter</kbd> to send or
   <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line.
5. Select **Stop** to cancel a response in progress.

The browser uploads one YAML snapshot when it creates the chat session. Later
questions in that session use the same backend-owned snapshot. Reload the page
to begin a new chat from the latest schedule.

## Data and limitations

The complete schedule YAML is sent to the configured AI backend and model
provider. People IDs, descriptions, rules, and dates may be sensitive. Use only
an approved provider and anonymize the schedule first when required.

Chat sessions use unguessable identifiers but do not have account
authentication yet. Sessions are stored in AI-backend memory and disappear
when that process restarts. Model answers may be incorrect, so verify them
against the schedule.

## Fix common problems

| Problem | What to do |
| --- | --- |
| Send fails immediately | Start the AI backend and verify `http://localhost:8001/health`. |
| Provider unavailable | Check `AI_PROVIDER_BASE_URL`, `AI_PROVIDER_API_KEY`, and provider availability. |
| Counts are unexpected | Return to the editor or Save and Load page, then reload Experimental AI. |
| An answer stops early | Send the question again. A cancelled or failed answer is not added to backend history. |
