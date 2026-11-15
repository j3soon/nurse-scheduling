<!-- SPDX-License-Identifier: AGPL-3.0-or-later
SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# Frontend Browser Storage

The frontend keeps a Schedule Spec, backend settings, and recent AI chats in the
browser. The Schedule Spec remains independent of saved chats. The backend owns AI
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
| `nurse-scheduling-spec` | Schedule Spec and Undo/Redo history. | No automatic expiry. |
| `nurse-scheduling-optimize-server-options` | Optimize backend endpoints, selected endpoint, remembered tokens, and saving `appVersion`. | No automatic expiry. |
| `nurse-scheduling-ai-history` | Recent conversation snapshots, activity times, saving `appVersion`, and a Clear history marker. | Entries expire seven days after activity. The clear marker has no automatic expiry. |
| `nurse-scheduling-ai-conversation` | Active conversation snapshot in `sessionStorage`. | Tab session, subject to the seven-day activity check. |
| `nurse-scheduling-ai-data` | Display preferences for reasoning, tools, turn costs, models, and Chinese conversion. | No automatic expiry. |
| `nurse-scheduling-ai-server` | Selected AI backend URL as a plain string. | No automatic expiry. |
| `nurse-scheduling-ai-auth` | Remembered AI tokens by backend endpoint. | No automatic expiry. |

<a id="schedule-data"></a>

### Schedule Spec

[Schedule Spec storage][schedule-storage] saves the Undo/Redo history and current
history index. Serialization omits generated groups and computed date items,
uses date strings for ranges, and escapes infinity values. Loading normalizes
Schedule Spec structures without a separate storage version.

External storage changes produce a warning without automatically importing
another tab's Schedule Spec. Browser tests can set
`window.__PLAYWRIGHT_WORKER_NAMESPACE__` to use
`nurse-scheduling-spec__<namespace>` instead of the production key.

Legacy Schedule Spec storage is normalized by `src/compat/scheduleSpec.ts`.
The loader reads `nurse-scheduling-spec` first. When that key is absent, it
validates `nurse-scheduling-data` and checks the current key again before writing.
If another tab has saved the current key, the loader uses that record. Otherwise,
it writes the current key and removes the old key. A failed write retains the
old record and its full history. Once the current key exists, writes from an
older tab to the old key are ignored. These checks reduce migration races.
`localStorage` does not provide an atomic read-and-write operation across tabs.
AI conversation snapshots and chat history can be discarded after an update.
They are excluded from the [browser migration guarantee](compatibility.md).

### Backend Settings and Credentials

[Optimize and Export][optimize-page] saves backend settings with the frontend
`appVersion`. The [AI page][ai-page] saves its selected backend and display
preferences separately, without version fields.

Tokens are saved only when explicitly remembered. The AI token record uses
`{ tokens }`, mapping backend endpoints to credentials. Forgetting a token removes
its entry, and an empty map removes the key. Clearing chat history does not clear
credentials. Conversation snapshots do not contain tokens.

## AI Chat Recovery

[Chat history][chat-history] stores `{ appVersion, entries, clearGeneration? }`.
Each entry contains a conversation snapshot and `lastActivityAt`. The backend endpoint and session
ID identify a conversation. The saving frontend version uses `appVersion`,
without a separate numeric storage version.

The [conversation parser][conversation-parser] validates snapshots from both
stores. A snapshot includes the transcript, activity and expiry times, synced
Schedule Spec YAML, browser-normalized Schedule Spec YAML, applied-run records, event
cursor, pending request metadata, optimization state, context usage, and costs.
The tab snapshot has no version envelope. Its `backendVersion` identifies the
AI backend rather than the frontend.

Each tab owns an in-memory conversation and event reader. During streaming,
[the chat hook][chat-hook] waits 200 ms before constructing a snapshot. It writes
tab recovery synchronously and queues shared history separately. A finished run,
a hidden page, navigation, or a conversation switch flushes the latest snapshot.
Failure in tab storage does not prevent a shared-history save.

The tab snapshot keeps `historyPending` until the first shared save succeeds.
Reload can retry that save unless Clear history has invalidated it. A delayed
save completion updates recovery metadata only for its original conversation
and preserves the latest transcript and cursor.
Closing the tab can interrupt queued shared saves, so page-close handlers do not
wait for them. Selecting a saved chat preserves the browser's current Schedule Spec.

### Retention and Removal

Chat actions and newly observed server event IDs update activity time. Reading
or selecting a saved chat does not renew it. History reads exclude expired
entries. The AI page also prunes storage on initialization and a one-minute
interval while mounted. Storage notifications refresh the list without writing.
Expired records can remain physically stored while the app is closed.

**Remove** and **Clear history** forget browser records without deleting backend
sessions. Forgetting the active chat leaves it visible but prevents later saves.
New chat, local forgetting, and session-unavailability handling clear the active
tab record.

Clear history also excludes chats already in progress in other tabs, including
first saves that have not completed. Retrying or reloading one of these chats
cannot add it back to Recent chats. Its open conversation remains usable. Only
chats started after Clear history completes can enter history again.

Each chat captures `historyGeneration` before its first session-creation request
and keeps it across failed creation attempts. It saves the marker in tab recovery
once a session exists. Clear history writes a new `clearGeneration` with
an empty entry list in one locked storage write. Every save checks that these
markers match. An absent marker means no Clear has occurred. Cleanup and removal
preserve the latest marker even when no entries remain. A failed Clear write
changes neither the marker nor the entries.

Individual Remove has no persistent deletion marker. A duplicated tab that copied
an unacknowledged first-save backup can recreate that chat after Remove. Use Clear
history when pending recovery from other tabs must also stay excluded.

Backend retention is separate. A chat can become unavailable after expiry or a
server restart even while a local record remains. Recent chats are a recovery
cache. Use **Export chat** to preserve a copy independently.

### Concurrent Tabs

Tabs keep separate active snapshots but share the recent-chat array. Save,
Remove, Clear history, and cleanup use the exclusive [Web Lock][web-locks]
named `nurse-scheduling-ai-history`. Each operation reads the current array
after acquiring the lock and completes its storage write before releasing it.
All open tabs must run the updated frontend to participate in this coordination.

Each conversation keeps one save in flight and only its latest waiting snapshot.
Navigation back to the AI page reuses its pending writer. Creation acknowledgements
also update the matching tab backup while the AI page is unmounted.
Forgetting clears the matching backup even when there are no mounted listeners.
Remove and Clear history cancel waiting saves for the open chat. Only its first
save can create a record. Later saves cannot recreate a missing entry.
Storage notifications refresh the list without replacing an open tab's transcript
or changing its event reader.

When browser locking is unavailable, shared history remains readable but cannot
be saved, removed, cleared, or pruned. The page shows a warning. The open chat and
tab recovery continue to work. This includes plain HTTP LAN origins where Web
Locks are unavailable.

Locking orders storage operations. It does not merge conflicting snapshots of the
same chat. `saveChatHistory` rejects a snapshot when the stored activity timestamp
is strictly newer. A tab receiving older events later can still have a newer
activity timestamp and overwrite a more advanced snapshot.

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
[web-locks]: https://www.w3.org/TR/web-locks/
