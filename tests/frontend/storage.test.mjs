import assert from "node:assert/strict";
import test from "node:test";

import { clearRecent, loadRecent, rememberLink } from "../../frontWeb/src/storage.js";

function memory() {
  const data = new Map();
  return {
    getItem(key) {
      return data.has(key) ? data.get(key) : null;
    },
    setItem(key, value) {
      data.set(key, String(value));
    },
    removeItem(key) {
      data.delete(key);
    },
  };
}

test("recent links stay local, newest first, and capped", () => {
  const storage = memory();
  for (let index = 0; index < 10; index += 1) {
    rememberLink(
      { shortUrl: `https://short.example/r/CODE${index}`, longUrl: `https://example.com/${index}` },
      storage,
    );
  }
  const items = loadRecent(storage);
  assert.equal(items.length, 8);
  assert.equal(items[0].shortUrl, "https://short.example/r/CODE9");
  rememberLink(
    { shortUrl: "https://short.example/r/CODE9", longUrl: "https://example.com/again" },
    storage,
  );
  const again = loadRecent(storage);
  assert.equal(again.filter((item) => item.shortUrl.endsWith("CODE9")).length, 1);
  assert.equal(again[0].longUrl, "https://example.com/again");
  clearRecent(storage);
  assert.deepEqual(loadRecent(storage), []);
});

test("corrupt storage reads as an empty list", () => {
  const storage = memory();
  storage.setItem("shortlink.recent", "{");
  assert.deepEqual(loadRecent(storage), []);
});
