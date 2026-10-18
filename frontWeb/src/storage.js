const KEY = "shortlink.recent";
const LIMIT = 8;

export function loadRecent(storage) {
  try {
    const parsed = JSON.parse(storage.getItem(KEY) || "[]");
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter(isEntry).slice(0, LIMIT);
  } catch {
    return [];
  }
}

export function rememberLink(entry, storage) {
  const next = [entry, ...loadRecent(storage).filter((item) => item.shortUrl !== entry.shortUrl)].slice(0, LIMIT);
  storage.setItem(KEY, JSON.stringify(next));
  return next;
}

export function clearRecent(storage) {
  storage.removeItem(KEY);
}

function isEntry(value) {
  return Boolean(
    value &&
      typeof value.shortUrl === "string" &&
      typeof value.longUrl === "string" &&
      value.shortUrl.startsWith("http"),
  );
}
