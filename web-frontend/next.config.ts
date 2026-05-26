import { withSentryConfig } from "@sentry/nextjs";
import type { NextConfig } from "next";
import { execSync } from "child_process";
import { resolve } from "path";
import { fileURLToPath } from "url";

const REPO_ROOT = resolve(fileURLToPath(new URL("..", import.meta.url)));

function getGitVersion(cwd: string = REPO_ROOT): string {
  try {
    // Try to get version from git describe (uses tags + commits)
    const command = `git -c ${JSON.stringify(`safe.directory=${cwd}`)} -C ${JSON.stringify(cwd)} describe --tags --always --dirty`;
    console.log(`Getting app version with: ${command}`);
    const version = execSync(command, {
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "pipe"],
    }).trim();
    console.log(`Resolved app version: ${version}`);
    return version;
  } catch (error) {
    const stderr = error instanceof Error && "stderr" in error
      ? String(error.stderr).trim()
      : String(error);
    console.warn(`Failed to resolve app version: ${stderr}`);
    return "v0.0.0-unknown";  // Fallback if git command fails (e.g., not a git repo)
  }
}

const appVersion = getGitVersion();
const sentryRelease = process.env.SENTRY_RELEASE || `nurse-scheduling@${appVersion}`;

const nextConfig: NextConfig = {
  /* config options here */
  output: 'export',
  env: {
    NEXT_PUBLIC_APP_VERSION: appVersion,
    NEXT_PUBLIC_GA_MEASUREMENT_ID: 'G-XGDWE4SWF7',
  },
};

export default withSentryConfig(nextConfig, {
  // For all available options, see:
  // https://www.npmjs.com/package/@sentry/webpack-plugin#options

  org: "j3soon",

  project: "nurse-scheduling",

  // Only print logs for uploading source maps in CI
  silent: !process.env.CI,

  release: {
    name: sentryRelease,
    setCommits: { auto: true },
  },

  // For all available options, see:
  // https://docs.sentry.io/platforms/javascript/guides/nextjs/manual-setup/

  // Upload a larger set of source maps for prettier stack traces (increases build time)
  widenClientFileUpload: true,

  // Uncomment to route browser requests to Sentry through a Next.js rewrite to circumvent ad-blockers.
  // This can increase your server load as well as your hosting bill.
  // Note: Check that the configured route will not match with your Next.js middleware, otherwise reporting of client-
  // side errors will fail.
  // tunnelRoute: "/monitoring",

  webpack: {
    // Enables automatic instrumentation of Vercel Cron Monitors. (Does not yet work with App Router route handlers.)
    // See the following for more information:
    // https://docs.sentry.io/product/crons/
    // https://vercel.com/docs/cron-jobs
    automaticVercelMonitors: true,

    // Tree-shaking options for reducing bundle size
    treeshake: {
      // Automatically tree-shake Sentry logger statements to reduce bundle size
      removeDebugLogging: true,
    },
  }
});
