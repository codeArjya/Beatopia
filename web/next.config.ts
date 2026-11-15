import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import type { NextConfig } from "next";

const repoRoot = path.join(__dirname, "..");

// The team keeps ONE .env at the repo root. Pull in only its NEXT_PUBLIC_* keys (never server secrets);
// real env vars and web/.env* files still win.
const rootEnv = path.join(repoRoot, ".env");
if (existsSync(rootEnv)) {
  for (const line of readFileSync(rootEnv, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*(NEXT_PUBLIC_[A-Z0-9_]+)\s*=\s*([^#]*?)\s*(#.*)?$/);
    if (m && process.env[m[1]] === undefined) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    // Vercel restores .next/cache between builds, and the Turbopack build cache in it handed back an
    // outdated compile of app/globals.css: production shipped the new markup with the old stylesheet
    // (empty `@layer components`, no design tokens). A cold build is ~20 s, so always build CSS fresh.
    turbopackFileSystemCacheForBuild: false,
  },
  turbopack: {
    // Repo root, so lib/api can import ../shared/fixtures (the single source of fixture truth).
    root: repoRoot,
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
