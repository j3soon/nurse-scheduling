// This file configures the initialization of Sentry on the server.
// The config you add here will be used whenever the server handles a request.
// https://docs.sentry.io/platforms/javascript/guides/nextjs/

import * as Sentry from "@sentry/nextjs";

const defaultSentryDsn = "https://e5bffd2f416c149dfb0d17751071c61d@o4510953883107328.ingest.us.sentry.io/4510953885401088";

Sentry.init({
  dsn: process.env.SENTRY_FRONTEND_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN || defaultSentryDsn,
  environment: process.env.SENTRY_ENVIRONMENT || process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT || "development",

  // Define how likely traces are sampled. Adjust this value in production, or use tracesSampler for greater control.
  tracesSampleRate: 1,

  // Enable logs to be sent to Sentry
  enableLogs: true,

  // Enable sending user PII (Personally Identifiable Information)
  // https://docs.sentry.io/platforms/javascript/guides/nextjs/configuration/options/#sendDefaultPii
  sendDefaultPii: true,
});

Sentry.setTag("app", "frontend");
