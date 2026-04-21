import { test } from 'node:test';
import assert from 'node:assert/strict';
import { levenshtein, findClosest } from '../../lib/args.js';

test('levenshtein: identical strings → 0', () => {
  assert.equal(levenshtein('generate', 'generate'), 0);
});

test('levenshtein: empty to non-empty returns length', () => {
  assert.equal(levenshtein('', 'abc'), 3);
  assert.equal(levenshtein('abc', ''), 3);
});

test('levenshtein: single-char transposition counted as 1 sub', () => {
  assert.equal(levenshtein('generate', 'genarate'), 1);
});

test('levenshtein: one deletion', () => {
  assert.equal(levenshtein('generat', 'generate'), 1);
});

test('levenshtein: two edits', () => {
  // "prjct" → "project": insert 'o', insert 'e'
  assert.equal(levenshtein('prjct', 'project'), 2);
});

test('findClosest: finds project for projct (distance 1)', () => {
  const suggestion = findClosest('projct', ['project', 'game', 'dry-run', 'debug']);
  assert.equal(suggestion, 'project');
});

test('findClosest: returns null when nothing within cap', () => {
  const suggestion = findClosest('xyzqqq', ['project', 'game', 'dry-run']);
  assert.equal(suggestion, null);
});

test('findClosest: short needles use tighter distance cap', () => {
  // "ab" → cap=1, so "abcd" (distance 2) must NOT match.
  const suggestion = findClosest('ab', ['abcd', 'zz']);
  assert.equal(suggestion, null);
});

test('findClosest: returns the closest match when two are within cap', () => {
  // "generat" is distance 1 from "generate", distance 3 from "migrate"
  const suggestion = findClosest('generat', ['generate', 'migrate']);
  assert.equal(suggestion, 'generate');
});

test('findClosest: handles empty candidates gracefully', () => {
  assert.equal(findClosest('anything', []), null);
  assert.equal(findClosest('anything', null), null);
});

test('findClosest: case-insensitive', () => {
  assert.equal(findClosest('GENERATE', ['generate']), 'generate');
});
