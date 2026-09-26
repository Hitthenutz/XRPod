// Called by the Raspberry Pi agent to report a sensor reading.
//
// The Pi is a device, not a logged-in user, so this is protected by a shared
// secret: the request must carry an `x-agent-key` header equal to the
// PI_AGENT_KEY app secret (set with `base44 secrets set PI_AGENT_KEY=...`).
import { createClientFromRequest } from "npm:@base44/sdk";
import { secrets } from "base44:runtime";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

// Constant-time comparison so the key can't be guessed byte-by-byte from timing.
function safeEqual(a: string, b: string): boolean {
  const enc = new TextEncoder();
  const ab = enc.encode(a);
  const bb = enc.encode(b);
  let diff = ab.length ^ bb.length;
  for (let i = 0; i < Math.max(ab.length, bb.length); i++) {
    diff |= (ab[i] ?? 0) ^ (bb[i] ?? 0);
  }
  return diff === 0;
}

const isNumber = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v);

export default async function handler(req: Request): Promise<Response> {
  if (req.method !== "POST") {
    return json({ error: "Method not allowed" }, 405);
  }

  const expectedKey = secrets.get("PI_AGENT_KEY");
  if (!expectedKey) {
    return json({ error: "PI_AGENT_KEY secret is not configured" }, 500);
  }
  const providedKey = req.headers.get("x-agent-key") ?? "";
  if (!safeEqual(providedKey, expectedKey)) {
    return json({ error: "Unauthorized" }, 401);
  }

  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return json({ error: "Body must be JSON" }, 400);
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return json({ error: "Body must be a JSON object" }, 400);
  }

  const missing = ["actual_temp_f", "actual_humidity_pct"].filter(
    (k) => !isNumber(body[k]),
  );
  if (missing.length) {
    return json(
      { error: `Missing or non-numeric field(s): ${missing.join(", ")}` },
      400,
    );
  }

  // Only pass through known fields, with the right types.
  const reading: Record<string, unknown> = {
    actual_temp_f: body.actual_temp_f,
    actual_humidity_pct: body.actual_humidity_pct,
    reading_source:
      typeof body.reading_source === "string" ? body.reading_source : "pi-agent",
  };
  if (typeof body.ac_running === "boolean") reading.ac_running = body.ac_running;
  if (typeof body.heater_running === "boolean") {
    reading.heater_running = body.heater_running;
  }
  if (isNumber(body.fan_rpm)) reading.fan_rpm = body.fan_rpm;
  if (typeof body.scent_active === "string") {
    reading.scent_active = body.scent_active;
  }

  try {
    const base44 = createClientFromRequest(req);
    const created = await base44.asServiceRole.entities.SensorReading.create(
      reading,
    );
    return json({ ok: true, id: created.id }, 201);
  } catch (err) {
    console.error("Failed to create SensorReading:", err);
    return json({ error: "Failed to store reading" }, 500);
  }
}
