import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The FastAPI backend runs on localhost:8000 alongside this app (see
  // ../start.sh). Rewrites happen server-side in the Next.js server, so
  // the browser only ever talks to this app's own externally-exposed port
  // -- no CORS involved, and only one port needs to be exposed by
  // Databricks Apps.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
