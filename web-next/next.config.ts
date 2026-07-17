import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep Playwright's dev server isolated from a developer's running instance.
  distDir: process.env.PLAYWRIGHT === "1" ? ".next-playwright" : ".next",
};

export default nextConfig;
