// Client-side preview of the server URL policy. The API remains authoritative.

const MAX_LENGTH = 2048;

export function validateLongUrl(value) {
  if (typeof value !== "string" || !value.trim()) {
    return { ok: false, message: "Enter a URL that starts with http:// or https://." };
  }
  const trimmed = value.trim();
  if (trimmed.length > MAX_LENGTH) {
    return { ok: false, message: "URLs must be 2048 characters or fewer." };
  }
  if (/[\u0000-\u0020\u007f]/.test(trimmed) || trimmed.includes("\\")) {
    return { ok: false, message: "That URL isn't valid." };
  }
  let url;
  try {
    url = new URL(trimmed);
  } catch {
    return { ok: false, message: "That URL isn't valid." };
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return { ok: false, message: "Enter a URL that starts with http:// or https://." };
  }
  if (url.username || url.password) {
    return { ok: false, message: "That URL can't include a username or password." };
  }
  const host = url.hostname.toLowerCase().replace(/\.$/, "");
  if (!host || !acceptableHost(host)) {
    return { ok: false, message: hostMessage(host) };
  }
  return { ok: true, url: trimmed };
}

function hostMessage(host) {
  if (isLocalName(host) || isNonPublicAddress(host)) {
    return "Local and private addresses can't be shortened.";
  }
  return "That URL isn't valid.";
}

function isLocalName(host) {
  return host === "localhost" || host.endsWith(".localhost") || host.endsWith(".local") || host.endsWith(".internal");
}

function isNonPublicAddress(host) {
  if (!(host.includes(":") || /^\d+$/.test(host) || /^[0-9.]+$/.test(host))) {
    return false;
  }
  return !acceptableHost(host);
}

function acceptableHost(host) {
  if (isLocalName(host)) {
    return false;
  }
  if (host.includes(":")) {
    return !isBlockedAddress(host);
  }
  if (/^\d+$/.test(host) || /^[0-9.]+$/.test(host)) {
    return !isBlockedAddress(host) && isPublicDottedOrDecimal(host);
  }
  const labels = host.split(".");
  if (labels.length < 2 || host.length > 253) {
    return false;
  }
  return labels.every((label) => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label));
}

function isPublicDottedOrDecimal(host) {
  if (/^\d+$/.test(host)) {
    const value = Number(host);
    if (!Number.isSafeInteger(value) || value < 0 || value > 0xffffffff) {
      return false;
    }
    return isPublicIPv4([
      (value >>> 24) & 255,
      (value >>> 16) & 255,
      (value >>> 8) & 255,
      value & 255,
    ]);
  }
  const octets = host.split(".").map(Number);
  if (octets.length !== 4) {
    return false;
  }
  const raw = host.split(".");
  if (raw.some((octet) => !/^\d+$/.test(octet) || Number(octet) > 255 || (octet.length > 1 && octet.startsWith("0")))) {
    return false;
  }
  return isPublicIPv4(octets);
}

function isPublicIPv4(octets) {
  const [a, b, c] = octets;
  if (a === 0 || a === 10 || a === 127 || a >= 224) return false;
  if (a === 169 && b === 254) return false;
  if (a === 172 && b >= 16 && b <= 31) return false;
  if (a === 192 && b === 168) return false;
  if (a === 100 && b >= 64 && b <= 127) return false;
  if (a === 192 && b === 0 && c === 2) return false;
  if (a === 198 && (b === 18 || b === 19 || b === 51)) return false;
  if (a === 203 && b === 0 && c === 113) return false;
  return true;
}

function isBlockedAddress(host) {
  const bare = host.replace(/^\[|\]$/g, "");
  if (bare === "::1" || bare === "0:0:0:0:0:0:0:1") return true;
  if (bare.startsWith("fc") || bare.startsWith("fd") || bare.startsWith("fe80")) return true;
  return false;
}
