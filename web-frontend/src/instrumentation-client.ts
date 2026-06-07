// This file configures the initialization of Sentry on the client.
// The added config here will be used whenever a users loads a page in their browser.
// https://docs.sentry.io/platforms/javascript/guides/nextjs/

import * as Sentry from "@sentry/nextjs";
import { getLatestSchedulingYamlForSentry } from "@/utils/sentrySchedulingState";

const isSentryDisabled = process.env.NEXT_PUBLIC_DISABLE_SENTRY === "1";

if (!isSentryDisabled) {
  Sentry.init({
    dsn: "https://e5bffd2f416c149dfb0d17751071c61d@o4510953883107328.ingest.us.sentry.io/4510953885401088",

    // Add optional integrations for additional features
    integrations: [
      Sentry.replayIntegration(),
      Sentry.feedbackIntegration({
        colorScheme: "light",
        enableScreenshot: true,
        isNameRequired: true,
        isEmailRequired: true,
      }),
    ],

    // Define how likely traces are sampled. Adjust this value in production, or use tracesSampler for greater control.
    tracesSampleRate: 1,
    // Enable logs to be sent to Sentry
    enableLogs: true,

    // Define how likely Replay events are sampled.
    // This sets the sample rate to be 10%. You may want this to be 100% while
    // in development and sample at a lower rate in production
    replaysSessionSampleRate: 0.1,

    // Define how likely Replay events are sampled when an error occurs.
    replaysOnErrorSampleRate: 1.0,

    // Enable sending user PII (Personally Identifiable Information)
    // https://docs.sentry.io/platforms/javascript/guides/nextjs/configuration/options/#sendDefaultPii
    sendDefaultPii: true,

    // Ref: https://docs.sentry.io/platforms/javascript/enriching-events/attachments/#add-or-modify-attachments-before-sending
    beforeSend(event, hint) {
      const yaml = getLatestSchedulingYamlForSentry();

      if (yaml) {
        hint.attachments = [
          ...(hint.attachments ?? []),
          {
            filename: "nurse-scheduling-state.yaml",
            data: yaml,
            contentType: "application/x-yaml",
          },
        ];

        // Ref: https://docs.sentry.io/platforms/react-native/tracing/instrumentation/custom-instrumentation/#adding-attributes-to-all-spans
        event.contexts = {
          ...event.contexts,
          scheduling_state: {
            attached: true,
            peopleIdsAnonymized: true,
            sizeBytes: new Blob([yaml]).size,
          },
        };
      }

      return event;
    },
  });
}

Sentry.setTag("app", "frontend");

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
