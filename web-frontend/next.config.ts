import type { NextConfig } from "next";
import { execSync } from "child_process";

function getGitVersion(): string {
  try {
    // Try to get version from git describe (uses tags + commits)
    return execSync("git describe --tags --always --dirty", { encoding: "utf-8" }).trim();
  } catch {
    return "unknown";
  }
}

const nextConfig: NextConfig = {
  /* config options here */
  output: 'export',
  basePath: process.env.GITHUB_REPOSITORY ? `/${process.env.GITHUB_REPOSITORY.split('/')[1]}` : '',
  env: {
    NEXT_PUBLIC_APP_VERSION: getGitVersion(),
    NEXT_PUBLIC_GA_MEASUREMENT_ID: 'G-XGDWE4SWF7',
  },
};

export default nextConfig;
