<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# Deployment and Compatibility

Every push to `dev` deploys the frontend, optimizer backend, AI backend, and
documentation together. The deployment replaces the previous development
services. Tagged release frontends can remain hosted and use newer optimizer
backends. An already-open development tab can require a reload after an update.

## Supported contracts

| Contract | Requirement |
| --- | --- |
| Tagged frontend → newer optimizer | Preserve the optimizer requests, responses, job controls, events, and downloads used by tagged release frontends. |
| Browser Schedule Specs and settings | Automatically migrate Schedule Specs, Undo/Redo history, settings, and saved backend selections when their stored format changes. |
| Experimental AI conversations | Client and server upgrade together. AI APIs, browser conversations, backend sessions, and chat history have no compatibility guarantee across updates or restarts. |

The current development frontend uses the current optimizer API. It does not
need to support an older optimizer backend. Python imports, sandbox filenames,
and developer-tool export formats can change with the same deployment.

Keep existing Schedule Spec YAML valid when only terminology changes. Schema
changes must state how tagged frontend input and saved browser input remain
usable.

### Tagged optimizer contract

| Frontend release | Advertised optimizer API version | Submission |
| --- | --- | --- |
| `v0.2.0` | `0.2.0` | `POST /optimize` with multipart `file`, `prettify`, and `timeout`. |

This frontend checks the advertised API version. The optimizer application
version can advance while the supported API version remains `0.2.0`. Existing
job routes, response fields, and workbook downloads remain available. The
release sends no bearer token, so it requires a deployment that permits those
requests under its authentication policy.

Record the optimizer contract when tagging a frontend release. Test its original
request and response formats against the current backend. Do not rename the
legacy fixtures together with the implementation.

## Implementation rules

Keep the current API and storage format separate from compatibility code.
Put required legacy route adapters and browser migrations in dedicated
`compat.py`, `compat.ts`, or `compat/` modules. Current application code uses
current names and formats. Avoid compatibility adapters for unsupported contracts.

For browser migration, read the current key first. Validate an older record
before writing its replacement, and remove the old key only after that write
succeeds. Preserve the original record on failure. AI conversation snapshots
and chat history are excluded from this migration guarantee.

Keep numbered database schema migrations needed to upgrade an installation.
They do not promise that older AI session contents remain readable. Validate
current AI session recovery and exports independently of legacy AI formats.
