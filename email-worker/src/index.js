// eldenstats.com catch-all email worker.
// PATCHED: always store the full raw email (not only when a 6-digit code is found),
// so link-based verification emails (Upwork, etc.) are retrievable via /debug.
// TTL raised 600s -> 3600s.

function extractVerificationCode(text) {
  const patterns = [
    /verification\s*code\s*(?:is)?[\s:]*(\d{6})/i,
    /(\d{6})\s*is\s*your\s*(?:Apple|verification)/i,
    /code[\s:]+(\d{6})/i,
    /passcode[\s:]+(\d{6})/i,
    /\b(\d{6})\b/,
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match) return match[1];
  }
  return null;
}

async function streamToString(stream) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let result = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    result += decoder.decode(value, { stream: true });
  }
  result += decoder.decode();
  return result;
}

const TTL = 3600; // 1 hour

export default {
  async email(message, env) {
    const to = message.to.toLowerCase();
    const from = message.from.toLowerCase();
    const rawEmail = await streamToString(message.raw);
    const code = extractVerificationCode(rawEmail);
    const meta = JSON.stringify({
      code,
      from,
      to,
      timestamp: new Date().toISOString(),
      subject: message.headers.get("subject") || "no subject",
    });
    // ALWAYS store both: the code/meta AND the full raw email (link emails have no code)
    await env.EMAIL_CODES.put(`code:${to}`, meta, { expirationTtl: TTL });
    await env.EMAIL_CODES.put(`email:${to}`, rawEmail.substring(0, 200000), { expirationTtl: TTL });
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    const cors = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };
    if (request.method === "OPTIONS") return new Response(null, { headers: cors });

    if (url.pathname === "/code" && request.method === "GET") {
      const email = url.searchParams.get("email")?.toLowerCase();
      if (!email) return json({ error: "Missing email parameter" }, 400, cors);
      const entry = await env.EMAIL_CODES.get(`code:${email}`);
      if (!entry) return json({ error: "No code found", email }, 404, cors);
      return new Response(entry, { headers: { "Content-Type": "application/json", ...cors } });
    }

    if (url.pathname === "/debug" && request.method === "GET") {
      const email = url.searchParams.get("email")?.toLowerCase();
      if (!email) return json({ error: "Missing email parameter" }, 400, cors);
      const rawEmail = await env.EMAIL_CODES.get(`email:${email}`);
      return json({ email, rawContent: rawEmail }, 200, cors);
    }

    if (url.pathname === "/health") {
      return json({ status: "ok", timestamp: new Date().toISOString() }, 200, cors);
    }

    return json({ error: "Not found", routes: ["/code?email=x", "/debug?email=x", "/health"] }, 404, cors);
  },
};

function json(obj, status, cors) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...cors },
  });
}
