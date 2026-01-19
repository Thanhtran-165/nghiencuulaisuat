/** @type {import('next').NextConfig} */
const { PHASE_DEVELOPMENT_SERVER } = require("next/constants");

module.exports = (phase) => {
  /**
   * Guardrail: isolate dev vs build output to avoid `.next` clobbering.
   * - Dev server writes to `.next-dev`
   * - Production build writes to `.next`
   */
  const distDir = phase === PHASE_DEVELOPMENT_SERVER ? ".next-dev" : ".next";

  return {
    reactStrictMode: true,
    distDir,
    allowedDevOrigins: ["127.0.0.1", "localhost"],
    async rewrites() {
      // Use 127.0.0.1 by default to avoid IPv6 localhost (::1) connection issues
      // when the backend only binds to 127.0.0.1.
      const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8001";
      return [
        {
          source: "/api/:path*",
          destination: `${backendUrl}/api/:path*`,
        },
      ];
    },
  };
};
