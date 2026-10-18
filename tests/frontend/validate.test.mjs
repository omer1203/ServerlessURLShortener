import assert from "node:assert/strict";
import test from "node:test";

import { validateLongUrl } from "../../frontWeb/src/validate.js";

test("accepts a normal https url", () => {
  assert.equal(validateLongUrl("  https://example.com/a  ").ok, true);
});

test("rejects empty, private, credentialed, and non-http urls", () => {
  for (const value of [
    "",
    "   ",
    "ftp://example.com",
    "javascript:alert(1)",
    "http://user:pass@example.com",
    "http://localhost/admin",
    "http://127.0.0.1",
    "http://10.0.0.8",
    "http://192.168.0.2",
    "http://169.254.169.254/latest/meta-data",
    "http://2130706433",
    "http://example",
  ]) {
    assert.equal(validateLongUrl(value).ok, false, value);
  }
});

test("does not flag a partial-looking value until it is actually invalid", () => {
  const result = validateLongUrl("https://example.com");
  assert.equal(result.ok, true);
  assert.equal(result.url, "https://example.com");
});
