# Privacy and Data Handling

This document describes the Nurse Scheduling System's data-handling behavior. Use nicknames or other non-identifying people IDs if a schedule may be sensitive. Self-host when your organization requires full control over processing, logging, and retention.

## Anonymization and Its Limits

The hosted optimization workflow anonymizes individual people IDs and removes descriptions by default. This means names used as people IDs are normally replaced before the schedule reaches the optimization server. A schedule without direct identifiers may not identify anyone by itself, but people-group IDs, dates, shift types, histories, preferences, and export configuration can still reveal information in context. Anonymization is not a guarantee, especially for malformed or unsupported data.

## Browser Storage

Scheduling data and up to 50 undo-history entries are stored in browser `localStorage` until cleared or replaced.

## Analytics and Error Reporting

The hosted frontend uses Google Analytics and Sentry for analytics, diagnostics, performance monitoring, feedback, and error reporting. Depending on the event, they may receive IP addresses, request headers, interaction metadata, logs, feedback contact details, and scheduling data.

- Sentry Session Replay samples video-like page interactions. Its current defaults mask text and input values and block media before transmission, but replay events and technical metadata are still sent.
- Feedback screenshots are optional and user-initiated. They are not automatically fully anonymized; users can redact sensitive areas with Sentry's **Hide** tool before submission.
- On frontend or backend errors, the current scheduling YAML may be attached to Sentry. Individual people IDs are anonymized and descriptions are removed where possible, but other sensitive information may remain. If backend anonymization fails, the original YAML may be attached.

Data received by Google Analytics and Sentry is subject to their policies and retention settings.

## Optimization Backend

Clicking **Optimize** sends the current scheduling YAML to the backend shown in the API Endpoint field, which may be the hosted server at `https://api.nursescheduling.org` or a user-selected server.

- **Anonymize schedule data** is enabled by default but may be disabled. It replaces individual people IDs and removes descriptions, not all potentially sensitive scheduling information.
- Submitted YAML, XLSX results, and operational job metadata are retained in the hosted backend's Redis job store for up to 24 hours after completion unless capacity cleanup or an explicit deletion removes them earlier. The hosted frontend attempts deletion after a successful download. Minimal reporting telemetry is stored separately as described below.
- Operational logs may include job IDs, pseudonymous client IDs, filenames, statuses, timing, and errors.
- The backend sets a pseudonymous client UUID cookie for up to 7 days.
- Docker Redis deployments retain minimal per-job telemetry for weekly reports, including job and pseudonymous client IDs, solver, lifecycle timestamps and state, queue and runtime durations, outcome, failure code, solver status, termination reason, configured timeout, and download count. Telemetry excludes scheduling inputs, filenames, IP addresses, and email addresses. Reporting does not remove telemetry. Rows expire 30 days after the end of their event week by default. Operators may send this telemetry through a configured reporting provider such as Mailgun.

## Opting Out While Using Hosted Services

Ad blockers and privacy-focused browser extensions may block Google Analytics and Sentry, depending on their configuration. They do not prevent scheduling data from being sent to the configured backend when you click **Optimize**.

## Self-Hosting

The project is open source so organizations can inspect its data handling and run the frontend and backend locally or on infrastructure they control:

- Disable frontend Sentry with `NEXT_PUBLIC_DISABLE_SENTRY=1`.
- Disable frontend server-side and backend Sentry with `DISABLE_SENTRY=1`.
- Disable the hosted optimization API with `NEXT_PUBLIC_DISABLE_HOSTED_OPTIMIZE_API=1`.
- Remove or disable Google Analytics before deploying a private frontend.

Self-hosters are responsible for securing their infrastructure and establishing appropriate logging and retention policies.
