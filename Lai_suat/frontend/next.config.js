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
  };
};
