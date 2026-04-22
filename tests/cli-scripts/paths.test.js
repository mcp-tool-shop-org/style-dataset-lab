import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolve, join } from 'node:path';
import { resolveSafeProjectPath, REPO_ROOT } from '../../lib/paths.js';

const fakeProject = resolve(REPO_ROOT, 'projects', 'star-freight');

test('resolveSafeProjectPath accepts relative paths inside project root', () => {
  const resolved = resolveSafeProjectPath(fakeProject, 'inputs/prompts/foo.json');
  assert.ok(resolved.startsWith(fakeProject), `expected inside project, got: ${resolved}`);
});

test('resolveSafeProjectPath rejects .. traversal escaping root', () => {
  assert.throws(
    () => resolveSafeProjectPath(fakeProject, '../../../etc/passwd'),
    (err) => err.code === 'INPUT_PATH_TRAVERSAL'
  );
});

test('resolveSafeProjectPath rejects absolute path outside root', () => {
  const outside = process.platform === 'win32' ? 'C:/Windows/system32' : '/etc/passwd';
  assert.throws(
    () => resolveSafeProjectPath(fakeProject, outside),
    (err) => err.code === 'INPUT_PATH_TRAVERSAL'
  );
});

test('resolveSafeProjectPath can use an alternate baseRoot', () => {
  const resolved = resolveSafeProjectPath(fakeProject, 'projects/star-freight/inputs/x.json', {
    baseRoot: REPO_ROOT,
  });
  assert.ok(resolved.startsWith(resolve(REPO_ROOT)));
});

test('resolveSafeProjectPath rejects empty/missing path', () => {
  assert.throws(
    () => resolveSafeProjectPath(fakeProject, ''),
    (err) => err.code === 'INPUT_MISSING_VALUE'
  );
  assert.throws(
    () => resolveSafeProjectPath(fakeProject, null),
    (err) => err.code === 'INPUT_MISSING_VALUE'
  );
});

test('resolveSafeProjectPath accepts deep nested relative path', () => {
  const resolved = resolveSafeProjectPath(fakeProject, 'outputs/approved/sub/nested/file.png');
  assert.ok(resolved.startsWith(fakeProject));
});
