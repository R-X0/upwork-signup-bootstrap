--7046ed72c61864f1e8c617a1fe7f7c584eff68f93dc23a1586c372eee3e3
Content-Disposition: form-data; name="index.js"

var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// src/index.ts
function extractVerificationCode(text) {
  const patterns = [
    /verification\s*code\s*(?:is)?[\s:]*(\d{6})/i,
    /(\d{6})\s*is\s*your\s*(?:Apple|verification)/i,
    /code[\s:]+(\d{6})/i,
    /passcode[\s:]+(\d{6})/i,
    // Generic: standalone 6-digit number (fallback)
    /\b(\d{6})\b/
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match) {
      return match[1];
    }
  }
  return null;
}
__name(extractVerificationCode, "extractVerificationCode");
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
__name(streamToString, "streamToString");
var index_default = {
  /** Handle incoming emails via Cloudflare Email Routing */
  async email(message, env) {
    const to = message.to.toLowerCase();
    const from = message.from.toLowerCase();
    console.log(`[Email Worker] Received email to: ${to} from: ${from}`);
    const rawEmail = await streamToString(message.raw);
    const code = extractVerificationCode(rawEmail);
    if (code) {
      console.log(`[Email Worker] Found code: ${code} for ${to}`);
      const entry = JSON.stringify({
        code,
        from,
        to,
        timestamp: (/* @__PURE__ */ new Date()).toISOString(),
        subject: message.headers.get("subject") || "no subject"
      });
      await env.EMAIL_CODES.put(`code:${to}`, entry, { expirationTtl: 600 });
      await env.EMAIL_CODES.put(`email:${to}`, rawEmail.substring(0, 5e3), { expirationTtl: 600 });
    } else {
      console.log(`[Email Worker] No verification code found in email to ${to}`);
      const entry = JSON.stringify({
        code: null,
        from,
        to,
        timestamp: (/* @__PURE__ */ new Date()).toISOString(),
        subject: message.headers.get("subject") || "no subject",
        bodyPreview: rawEmail.substring(0, 500)
      });
      await env.EMAIL_CODES.put(`code:${to}`, entry, { expirationTtl: 600 });
    }
  },
  /** HTTP handler - API to retrieve codes */
  async fetch(request, env) {
    const url = new URL(request.url);
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type"
    };
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }
    if (url.pathname === "/code" && request.method === "GET") {
      const email = url.searchParams.get("email")?.toLowerCase();
      if (!email) {
        return new Response(JSON.stringify({ error: "Missing email parameter" }), {
          status: 400,
          headers: { "Content-Type": "application/json", ...corsHeaders }
        });
      }
      const entry = await env.EMAIL_CODES.get(`code:${email}`);
      if (!entry) {
        return new Response(JSON.stringify({ error: "No code found", email }), {
          status: 404,
          headers: { "Content-Type": "application/json", ...corsHeaders }
        });
      }
      return new Response(entry, {
        headers: { "Content-Type": "application/json", ...corsHeaders }
      });
    }
    if (url.pathname === "/debug" && request.method === "GET") {
      const email = url.searchParams.get("email")?.toLowerCase();
      if (!email) {
        return new Response(JSON.stringify({ error: "Missing email parameter" }), {
          status: 400,
          headers: { "Content-Type": "application/json", ...corsHeaders }
        });
      }
      const rawEmail = await env.EMAIL_CODES.get(`email:${email}`);
      return new Response(JSON.stringify({ email, rawContent: rawEmail }), {
        headers: { "Content-Type": "application/json", ...corsHeaders }
      });
    }
    if (url.pathname === "/health") {
      return new Response(JSON.stringify({ status: "ok", timestamp: (/* @__PURE__ */ new Date()).toISOString() }), {
        headers: { "Content-Type": "application/json", ...corsHeaders }
      });
    }
    return new Response(JSON.stringify({ error: "Not found", routes: ["/code?email=x", "/debug?email=x", "/health"] }), {
      status: 404,
      headers: { "Content-Type": "application/json", ...corsHeaders }
    });
  }
};
export {
  index_default as default
};
//# sourceMappingURL=index.js.map

--7046ed72c61864f1e8c617a1fe7f7c584eff68f93dc23a1586c372eee3e3--
