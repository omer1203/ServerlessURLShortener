import assert from "node:assert/strict";
import test from "node:test";

import { interpretShortenResponse, safeHttpUrl } from "../../frontWeb/src/client.js";

test("accepts the shorten contract", () => {
  const result = interpretShortenResponse(201, {
    short_code: "ABC123",
    short_url: "https://short.example/r/ABC123",
    long_url: "https://example.com/article",
    created_at: "2026-10-18T00:00:00Z",
    expires_at: null,
  });
  assert.equal(result.ok, true);
  assert.equal(result.shortUrl, "https://short.example/r/ABC123");
  assert.equal(result.longUrl, "https://example.com/article");
});

test("rejects unsafe or incomplete payloads", () => {
  assert.equal(
    interpretShortenResponse(201, {
      short_code: "ABC123",
      short_url: "javascript:alert(1)",
      long_url: "https://example.com",
    }).ok,
    false,
  );
  assert.equal(interpretShortenResponse(201, { short_code: "ABC123" }).ok, false);
  assert.equal(safeHttpUrl("http://user:pass@example.com"), null);
});

test("uses server error text and a specific rate-limit message", () => {
  assert.equal(
    interpretShortenResponse(400, { error: "Enter a URL that starts with http:// or https://.", code: "invalid_url" })
      .message,
    "Enter a URL that starts with http:// or https://.",
  );
  assert.match(interpretShortenResponse(429, {}).message, /Too many requests/);
  assert.equal(interpretShortenResponse(500, { error: "<html>secret</html>" }).message.includes("<"), false);
  assert.match(interpretShortenResponse(503, null).message, /unavailable/);
});
