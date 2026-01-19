#!/usr/bin/env node
/**
 * Automatic Next.js Dev Cache Invalidation
 *
 * This script ensures build cache is always valid by computing a signature
 * from Next.js version + lockfile hash. If signature changes, cache is cleared.
 *
 * Usage: node scripts/ensure_dev_cache.mjs
 *
 * Run automatically by: npm predev hook
 */

import { readFileSync, existsSync, rmSync, writeFileSync, mkdirSync, readdirSync } from 'fs';
import { createHash } from 'crypto';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT = join(__dirname, '..');

// Configuration
const DEV_DIST_DIR = '.next-dev';
const CACHE_DIRS = [DEV_DIST_DIR, '.turbo'];
const SIGNATURE_FILE = join(ROOT, DEV_DIST_DIR, 'cache-signature.json');

/**
 * Detect a common corruption/mismatch:
 * - `.next-dev` is missing expected dev artifacts (e.g. main-app.js),
 *   typically due to concurrent dev servers or partial cache writes.
 *
 * This mismatch causes assets like:
 *   /_next/static/chunks/main-app.js
 *   /_next/static/chunks/app/page.js
 *   /_next/static/css/app/layout.css
 * to return 404, leaving pages stuck at SSR loading states.
 */
function detectDevAssetMismatch() {
  const reasons = [];

  const chunksDir = join(ROOT, DEV_DIST_DIR, 'static', 'chunks');
  const cssDir = join(ROOT, DEV_DIST_DIR, 'static', 'css');

  const devMainApp = join(chunksDir, 'main-app.js');
  const devLayoutCss = join(cssDir, 'app', 'layout.css');

  // If `.next-dev` exists but expected dev artifacts are missing while production-like ones exist.
  if (existsSync(chunksDir) && !existsSync(devMainApp)) {
    try {
      const entries = readdirSync(chunksDir);
      const hasProdMain = entries.some((n) => /^main-app-.*\.js$/.test(n));
      const hasProdAppPage = entries.some((n) => /^app\/page-.*\.js$/.test(n)) ||
        entries.some((n) => /^app\/page.*\.js$/.test(n)) ||
        existsSync(join(chunksDir, 'app')); // fallback
      if (hasProdMain) {
        reasons.push('Detected production chunks (main-app-*.js) but dev chunk main-app.js is missing');
      }
      // `app/page` may be in a subdir; the presence of hashed main-app is already a strong signal.
      if (hasProdMain && hasProdAppPage) {
        reasons.push('Detected hashed app chunks while starting dev server');
      }
    } catch {
      // ignore
    }
  }

  if (existsSync(cssDir) && !existsSync(devLayoutCss)) {
    try {
      const cssEntries = readdirSync(cssDir).filter((n) => n.endsWith('.css'));
      const hasHashedCss = cssEntries.some((n) => /^[0-9a-f]{8,}\.css$/.test(n));
      if (hasHashedCss) {
        reasons.push('Detected hashed CSS output but dev CSS app/layout.css is missing');
      }
    } catch {
      // ignore
    }
  }

  // Common sign of concurrent dev servers
  if (existsSync(join(ROOT, DEV_DIST_DIR, 'cache 2'))) {
    reasons.push(`Detected duplicate cache dir: ${DEV_DIST_DIR}/cache 2 (likely concurrent dev servers)`);
  }

  return reasons;
}

/**
 * Compute hash of a file
 */
function hashFile(filepath) {
  try {
    const content = readFileSync(filepath, 'utf-8');
    return createHash('sha256').update(content).digest('hex');
  } catch (error) {
    console.warn(`⚠️  Warning: Cannot read ${filepath}:`, error.message);
    return null;
  }
}

/**
 * Extract Next.js version from package.json
 */
function getNextVersion() {
  try {
    const pkgPath = join(ROOT, 'package.json');
    const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8'));

    // Check dependencies and devDependencies
    const nextVersion = pkg.dependencies?.next || pkg.devDependencies?.next;

    if (!nextVersion) {
      throw new Error('Next.js not found in dependencies');
    }

    // Extract version number (handle ^, ~, >= prefixes)
    const versionMatch = nextVersion.match(/[\d.]+/);
    return versionMatch ? versionMatch[0] : nextVersion;
  } catch (error) {
    console.warn('⚠️  Warning: Cannot extract Next.js version:', error.message);
    return 'unknown';
  }
}

/**
 * Compute current cache signature
 */
function computeSignature() {
  // 1. Next.js version
  const nextVersion = getNextVersion();

  // 2. Lockfile hash
  const lockFiles = [
    join(ROOT, 'package-lock.json'),
    join(ROOT, 'yarn.lock'),
    join(ROOT, 'pnpm-lock.yaml'),
  ];

  let lockHash = null;
  for (const lockFile of lockFiles) {
    if (existsSync(lockFile)) {
      lockHash = hashFile(lockFile);
      console.log(`📦 Lockfile: ${lockFile.split('/').pop()}`);
      break;
    }
  }

  if (!lockHash) {
    console.warn('⚠️  Warning: No lockfile found, signature may be unreliable');
  }

  // 3. Create signature
  const signature = {
    nextVersion,
    lockHash: lockHash || 'no-lockfile',
    timestamp: new Date().toISOString(),
  };

  return signature;
}

/**
 * Load saved signature from previous run
 */
function loadSavedSignature() {
  try {
    if (!existsSync(SIGNATURE_FILE)) {
      return null;
    }
    const content = readFileSync(SIGNATURE_FILE, 'utf-8');
    return JSON.parse(content);
  } catch (error) {
    console.warn('⚠️  Warning: Cannot load saved signature:', error.message);
    return null;
  }
}

/**
 * Save current signature
 */
function saveSignature(signature) {
  try {
    const dir = dirname(SIGNATURE_FILE);
    if (!existsSync(dir)) {
      mkdirSync(dir, { recursive: true });
    }
    writeFileSync(SIGNATURE_FILE, JSON.stringify(signature, null, 2));
  } catch (error) {
    console.warn('⚠️  Warning: Cannot save signature:', error.message);
  }
}

/**
 * Safely remove directory recursively
 */
function removeDir(dirpath) {
  if (!existsSync(dirpath)) {
    return false;
  }

  try {
    // Node.js 14.14.0+
    rmSync(dirpath, { recursive: true, force: true });
    return true;
  } catch (error) {
    console.warn(`⚠️  Warning: Cannot remove ${dirpath}:`, error.message);
    return false;
  }
}

/**
 * Main execution
 */
function main() {
  console.log('🔍 Checking dev cache validity...\n');

  const current = computeSignature();
  const saved = loadSavedSignature();
  const mismatchReasons = detectDevAssetMismatch();

  console.log(`Current signature:`);
  console.log(`  Next.js version: ${current.nextVersion}`);
  console.log(`  Lockfile hash: ${current.lockHash?.substring(0, 16)}...`);
  console.log('');

  if (!saved) {
    console.log('✨ No previous signature found (first run or manual cache clear)');
    console.log('📝 Saving current signature...');
    saveSignature(current);
    return;
  }

  console.log(`Previous signature:`);
  console.log(`  Next.js version: ${saved.nextVersion}`);
  console.log(`  Lockfile hash: ${saved.lockHash?.substring(0, 16)}...`);
  console.log(`  Last updated: ${saved.timestamp}`);
  console.log('');

  // Compare signatures
  const versionChanged = current.nextVersion !== saved.nextVersion;
  const lockChanged = current.lockHash !== saved.lockHash;

  if (mismatchReasons.length > 0 || versionChanged || lockChanged) {
    console.log('🔄 Cache signature changed! Clearing build cache...\n');

    const reasons = [];
    mismatchReasons.forEach((r) => reasons.push(r));
    if (versionChanged) reasons.push(`Next.js version: ${saved.nextVersion} → ${current.nextVersion}`);
    if (lockChanged) reasons.push('Lockfile content changed');

    console.log('Reasons:');
    reasons.forEach(reason => console.log(`  - ${reason}`));
    console.log('');

    let clearedCount = 0;
    for (const cacheDir of CACHE_DIRS) {
      const fullPath = join(ROOT, cacheDir);
      if (removeDir(fullPath)) {
        console.log(`🗑️  Removed: ${cacheDir}`);
        clearedCount++;
      } else {
        console.log(`ℹ️  Skipped: ${cacheDir} (not found)`);
      }
    }

    if (clearedCount > 0) {
      console.log('');
      console.log('✅ Cache cleared successfully');
    }

    console.log('📝 Saving new signature...');
    saveSignature(current);
  } else {
    console.log('✅ Cache signature unchanged - no action needed');
    console.log(`ℹ️  Cache is valid since ${new Date(saved.timestamp).toLocaleString()}`);
  }
}

// Run
main();
