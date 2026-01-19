#!/usr/bin/env node
/**
 * Kill any `next dev` processes that belong to THIS frontend project.
 *
 * Why: running multiple Next dev servers (or deleting/overwriting `.next-dev` while a dev
 * server is running) can corrupt the dev output and cause CSS/JS assets to 404,
 * leaving pages stuck at SSR "Đang tải...".
 */

import { execFileSync } from "child_process";
import process from "process";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PROJECT_ROOT = join(__dirname, "..");

const args = new Set(process.argv.slice(2));
const ignoreMissing = args.has("--ignore-missing");
const quiet = args.has("--quiet");

function log(msg) {
  if (!quiet) console.log(msg);
}

function psLines() {
  try {
    const out = execFileSync("ps", ["ax", "-o", "pid=,command="], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    });
    return out
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
  } catch {
    return [];
  }
}

function isNextDevForThisProject(cmd) {
  // Match both:
  // - `node .../frontend/node_modules/.bin/next dev ...`
  // - `node .../frontend/node_modules/.bin/cross-env ... next dev ...`
  //
  // Key signals:
  // - command references this project root (frontend/)
  // - command includes "next dev"
  return cmd.includes(PROJECT_ROOT) && /\bnext\s+dev\b/.test(cmd);
}

function parsePidAndCommand(line) {
  const firstSpace = line.indexOf(" ");
  if (firstSpace === -1) return null;
  const pidStr = line.slice(0, firstSpace).trim();
  const cmd = line.slice(firstSpace + 1).trim();
  const pid = Number(pidStr);
  if (!Number.isFinite(pid) || pid <= 0) return null;
  return { pid, cmd };
}

function isAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function killPid(pid, signal) {
  try {
    process.kill(pid, signal);
    return true;
  } catch {
    return false;
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function main() {
  const me = process.pid;
  const candidates = psLines()
    .map(parsePidAndCommand)
    .filter(Boolean)
    .filter(({ pid, cmd }) => pid !== me && isNextDevForThisProject(cmd));

  const pids = Array.from(new Set(candidates.map((c) => c.pid)));

  if (pids.length === 0) {
    if (!ignoreMissing) {
      log("ℹ️  No running `next dev` process found for this project.");
    }
    process.exit(0);
  }

  log(`🛑 Stopping existing Next dev server(s): ${pids.join(", ")}`);

  // Try graceful stop first
  for (const pid of pids) killPid(pid, "SIGTERM");
  await sleep(800);

  // Force kill if still alive
  const stillAlive = pids.filter(isAlive);
  if (stillAlive.length > 0) {
    log(`⚠️  Force killing remaining PID(s): ${stillAlive.join(", ")}`);
    for (const pid of stillAlive) killPid(pid, "SIGKILL");
    await sleep(300);
  }

  const remaining = pids.filter(isAlive);
  if (remaining.length > 0) {
    console.error(`❌ Failed to stop PID(s): ${remaining.join(", ")}`);
    process.exit(1);
  }

  log("✅ Stopped.");
}

await main();
