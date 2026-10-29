<!-- SPDX-License-Identifier: AGPL-3.0-or-later
SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# Frontend Browser Storage

The frontend keeps schedule data, backend settings, and recent AI chats in the
browser. Schedule data remains independent of saved chats. The backend owns AI
execution and retains session data separately.

## Storage Scope

`localStorage` is shared by tabs on the same origin and survives browser
restarts. `sessionStorage` belongs to one tab's page session and survives reloads
and same-tab navigation. A duplicated tab can start with a copy of the original
tab's session storage, but later writes remain separate. Browser session
restoration can also preserve tab storage after a restart.

The origin consists of the frontend's scheme, hostname, and port. Selecting a
different backend does not change where browser records are stored. Inspect
records in browser DevTools under **Application → Local Storage** and
**Session Storage**, selecting the frontend origin.

Neither store encrypts application records. Browser eviction or clearing site
data can remove them. The frontend does not directly create IndexedDB databases
or cookies. Browser caches and third-party SDK storage are outside this inventory.

## Storage Keys

All records below use `localStorage` except the active conversation.

| Key | Contents | Lifetime |
| --- | --- | --- |
| `nurse-scheduling-data` | Schedule data and Undo/Redo history. | No automatic expiry. |
| `nurse-scheduling-optimize-server-options` | Optimize backend endpoints, selected endpoint, remembered tokens, and saving `appVersion`. | No automatic expiry. |
| `nurse-scheduling-ai-history` | Recent conversation snapshots and activity times, with saving `appVersion`. | Seven days after chat activity. |
| `nurse-scheduling-ai-conversation` | Active conversation snapshot in `sessionStorage`. | Tab session, subject to the seven-day activity check. |
| `nurse-scheduling-ai-data` | Visibility preferences for reasoning, tools, turn costs, and models. | No automatic expiry. |
| `nurse-scheduling-ai-server` | Selected AI backend URL as a plain string. | No automatic expiry. |
| `nurse-scheduling-ai-auth` | Remembered AI tokens by backend endpoint. | No automatic expiry. |

### Schedule Data

[Schedule storage][schedule-storage] saves the Undo/Redo history and current
history index. Serialization omits generated groups and computed date items,
uses date strings for ranges, and escapes infinity values. Loading normalizes
schedule structures without a separate storage version.

External storage changes produce a warning without automatically importing
another tab's schedule data. Browser tests can set
`window.__PLAYWRIGHT_WORKER_NAMESPACE__` to use
`nurse-scheduling-data__<namespace>` instead of the production key.

### Backend Settings and Credentials

[Optimize and Export][optimize-page] saves backend settings with the frontend
`appVersion`. The [AI page][ai-page] saves its selected backend and display
preferences separately, without version fields.

Tokens are saved only when explicitly remembered. The AI token record uses
`{ tokens }`, mapping backend endpoints to credentials. Forgetting a token removes
its entry, and an empty map removes the key. Clearing chat history does not clear
credentials. Conversation snapshots do not contain tokens.

## AI Chat Recovery

[Chat history][chat-history] stores `{ appVersion, entries }`. Each entry contains
a conversation snapshot and `lastActivityAt`. The backend endpoint and session
ID identify a conversation. The saving frontend version uses `appVersion`,
without a separate numeric storage version.

The [conversation parser][conversation-parser] validates snapshots from both
stores. A snapshot includes the transcript, activity and expiry times, synced
schedule YAML, browser-normalized schedule YAML, applied-run records, event
cursor, pending request metadata, optimization state, context usage, and costs.
The tab snapshot has no version envelope. Its `backendVersion` identifies the
AI backend rather than the frontend.

Each tab owns an in-memory conversation and event reader. After state changes,
[the chat hook][chat-hook] waits 200 ms before constructing a snapshot and writing
it to tab storage, then shared history. These are independent writes. Failure in
tab storage does not prevent an attempt to save shared history. Leaving the page,
unmounting the chat, or switching conversations flushes the pending snapshot.
Selecting a saved chat preserves the browser's current schedule data.

### Retention and Removal

Chat actions and newly observed server event IDs update activity time. Reading
or selecting a saved chat does not renew it. History reads exclude expired
entries. The AI page also prunes storage on initialization, storage-change
notifications, and a one-minute interval while mounted. Expired records can
remain physically stored while the app is closed.

**Remove** and **Clear history** forget browser records without deleting backend
sessions. Forgetting the active chat leaves it visible but prevents later saves.
New chat, local forgetting, and session-unavailability handling clear the active
tab record.

Backend retention is separate. A chat can become unavailable after expiry or a
server restart even while a local record remains. Recent chats are a recovery
cache. Use **Export chat** to preserve a copy independently.

### Concurrent Tabs

Tabs keep separate active snapshots but share the recent-chat array.
`saveChatHistory` rejects a snapshot when the stored activity timestamp is
strictly newer. Ordinary updates cannot recreate a missing entry. Storage
notifications refresh the list and detect forgotten chats without replacing an
open tab's transcript or changing its event reader.

These checks do not make shared history transactional. A tab receiving older
events later can have a newer activity timestamp and overwrite a more advanced
snapshot. Concurrent writes to the whole array can also lose another chat's
update or restore an entry removed by another tab. Storage notifications do not
lock writers.

Overwrites do not change another open tab's in-memory conversation or backend
execution. Restoring an older snapshot can require additional backend replay.
Recovery depends on the backend still retaining the missing events.

## Data Kept in Memory

Chat drafts, selected attachment bytes, preview URLs, speech recognition state,
active readers, abort controllers, and locally queued messages remain in memory.
Saved pending request metadata does not preserve drafts or selected file bytes.
The backend can retain submitted steering independently of the local queue.

Optimize job state, progress, downloaded artifacts, and temporary download URLs
also remain in memory. Solver controls are not included in saved backend
settings. Uploaded chat files and generated archives remain on the backend.
Listing a file in the UI does not store its bytes in browser storage. Files saved
through browser downloads are outside these storage keys.

[schedule-storage]: https://github.com/j3soon/nurse-scheduling/blob/dev/web-frontend/src/hooks/schedulingStorage.ts
[optimize-page]: https://github.com/j3soon/nurse-scheduling/blob/dev/web-frontend/src/app/optimize-and-export/page.tsx
[ai-page]: https://github.com/j3soon/nurse-scheduling/blob/dev/web-frontend/src/app/experimental-ai/page.tsx
[chat-history]: https://github.com/j3soon/nurse-scheduling/blob/dev/web-frontend/src/app/experimental-ai/chatHistory.ts
[conversation-parser]: https://github.com/j3soon/nurse-scheduling/blob/dev/web-frontend/src/app/experimental-ai/chatConversation.ts
[chat-hook]: https://github.com/j3soon/nurse-scheduling/blob/dev/web-frontend/src/app/experimental-ai/useAiChat.ts
