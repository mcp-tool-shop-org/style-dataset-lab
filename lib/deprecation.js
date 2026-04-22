/**
 * Deprecation warning helper — fires once per flag per process.
 */

const warned = new Set();

export function warnDeprecated(oldFlag, newFlag) {
  const key = `${oldFlag}→${newFlag}`;
  if (warned.has(key)) return;
  warned.add(key);
  process.stderr.write(
    `\x1b[33m⚠ --${oldFlag} is deprecated and will be removed in v4.0. Use --${newFlag} instead.\x1b[0m\n`
  );
}
