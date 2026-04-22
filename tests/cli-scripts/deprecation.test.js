import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DEPRECATION_PATH = join(__dirname, '..', '..', 'lib', 'deprecation.js');
const PACKAGE_JSON_PATH = join(__dirname, '..', '..', 'package.json');

test('deprecation notice does not lie about the current major version', () => {
  const src = readFileSync(DEPRECATION_PATH, 'utf-8');
  const pkg = JSON.parse(readFileSync(PACKAGE_JSON_PATH, 'utf-8'));
  const currentMajor = Number.parseInt(pkg.version.split('.')[0], 10);

  // Grab any "v<N>.<M>" or "v<N>" target from the deprecation string.
  const match = src.match(/removed in v(\d+)(?:\.(\d+))?/);
  assert.ok(match, 'deprecation.js must contain a "removed in vX" target');
  const target = Number.parseInt(match[1], 10);
  assert.ok(
    target > currentMajor,
    `Deprecation targets v${target} but package is v${pkg.version}; the string is stale.`
  );
});
