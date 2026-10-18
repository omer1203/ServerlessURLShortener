const CODE = /^[A-Z0-9]{6}$/;

export function safeHttpUrl(value) {
  if (typeof value !== "string" || value.length > 4096) {
    return null;
  }
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return null;
    }
    if (url.username || url.password) {
      return null;
    }
    return value;
  } catch {
    return null;
  }
}

export function interpretShortenResponse(status, body) {
  if (status === 201 || status === 200) {
    const shortUrl = safeHttpUrl(body && body.short_url);
    const longUrl = safeHttpUrl(body && body.long_url);
    const shortCode = body && typeof body.short_code === "string" ? body.short_code : "";
    if (!shortUrl || !longUrl || !CODE.test(shortCode)) {
      return { ok: false, message: "The service returned an unexpected response." };
    }
    return {
      ok: true,
      shortUrl,
      longUrl,
      shortCode,
      createdAt: typeof body.created_at === "string" ? body.created_at : null,
      expiresAt: typeof body.expires_at === "string" ? body.expires_at : null,
    };
  }
  if (status === 429) {
    return { ok: false, message: "Too many requests. Wait a moment and try again." };
  }
  const serverMessage = body && typeof body.error === "string" ? body.error.trim() : "";
  if (serverMessage && serverMessage.length <= 180 && !serverMessage.includes("<")) {
    return { ok: false, message: serverMessage };
  }
  if (status >= 500) {
    return { ok: false, message: "The shortener is unavailable. Try again shortly." };
  }
  return { ok: false, message: "That URL couldn't be shortened." };
}
