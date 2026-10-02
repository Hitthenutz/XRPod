// Called by the Raspberry Pi agent to report a sensor reading.
//
// The Pi is a device, not a logged-in user, so this is protected by a shared
// secret: the request must carry an `x-agent-key` header equal to the
// PI_AGENT_KEY app secret (set with `base44 secrets set PI_AGENT_KEY=...`).
import { createClientFromRequest } from "npm:@base44/sdk";
import { secrets } from "base44:runtime";

// A reading is ~200 bytes; anything much bigger is a bug or abuse.
const MAX_BODY_BYTES = 4096;
const MAX_STRING_LENGTH = 64;

// Plausible ranges; values outside them are a sensor fault. Keep in sync
// with TEMP_RANGE_F / HUMIDITY_RANGE_PCT in pi-agent/agent.py.
const READING_RANGES: Record<string, [number, number]> = {
  actual_temp_f: [-40, 185],
  actual_humidity_pct: [0, 100],
  fan_rpm: [0, 50000],
};

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

const isShortString = (v: unknown): v is string =>
  typeof v === "string" && v.length > 0 && v.length <= MAX_STRING_LENGTH;

function checkRange(field: string, value: number): string | null {
  const [lo, hi] = READING_RANGES[field];
  return value >= lo && value <= hi ? null : `${field} must be between ${lo} and ${hi}`;
}

// Returns the reading to store, or a list of problems. Only known fields with
// the right types are passed through, because the write uses service role.
function validate(
  body: Record<string, unknown>,
): { reading: Record<string, unknown> } | { errors: string[] } {
  const errors: string[] = [];
  const reading: Record<string, unknown> = { reading_source: "pi-agent" };

  for (const field of ["actual_temp_f", "actual_humidity_pct"]) {
    const value = body[field];
    if (!isNumber(value)) {
      errors.push(`${field} is required and must be a number`);
      continue;
    }
    const rangeError = checkRange(field, value);
    if (rangeError) errors.push(rangeError);
    else reading[field] = value;
  }

  // Optional fields: absent or null is fine, a wrong type is an error.
  const present = (field: string) => body[field] !== undefined && body[field] !== null;

  for (const field of ["ac_running", "heater_running"]) {
    if (!present(field)) continue;
    if (typeof body[field] === "boolean") reading[field] = body[field];
    else errors.push(`${field} must be a boolean`);
  }

  if (present("fan_rpm")) {
    const rpm = body.fan_rpm;
    if (!isNumber(rpm)) errors.push("fan_rpm must be a number");
    else {
      const rangeError = checkRange("fan_rpm", rpm);
      if (rangeError) errors.push(rangeError);
      else reading.fan_rpm = rpm;
    }
  }

  for (const field of ["scent_active", "reading_source"]) {
    if (!present(field)) continue;
    if (isShortString(body[field])) reading[field] = body[field];
    else errors.push(`${field} must be a string of 1-${MAX_STRING_LENGTH} characters`);
  }

  return errors.length ? { errors } : { reading };
}

export default async function handler(req: Request): Promise<Response> {
  try {
    if (req.method !== "POST") {
      return json({ error: "Method not allowed" }, 405);
    }

    let expectedKey: string | undefined;
    try {
      expectedKey = secrets.get("PI_AGENT_KEY");
    } catch (err) {
      console.error("Couldn't read PI_AGENT_KEY secret:", err);
    }
    if (!expectedKey) {
      return json({ error: "PI_AGENT_KEY secret is not configured" }, 500);
    }
    const providedKey = req.headers.get("x-agent-key") ?? "";
    if (!safeEqual(providedKey, expectedKey)) {
      return json({ error: "Unauthorized" }, 401);
    }

    const declaredLength = Number(req.headers.get("content-length") ?? "0");
    if (declaredLength > MAX_BODY_BYTES) {
      return json({ error: `Body larger than ${MAX_BODY_BYTES} bytes` }, 413);
    }
    let text: string;
    try {
      text = await req.text();
    } catch {
      return json({ error: "Couldn't read request body" }, 400);
    }
    if (new TextEncoder().encode(text).length > MAX_BODY_BYTES) {
      return json({ error: `Body larger than ${MAX_BODY_BYTES} bytes` }, 413);
    }

    let body: unknown;
    try {
      body = JSON.parse(text);
    } catch {
      return json({ error: "Body must be JSON" }, 400);
    }
    if (!body || typeof body !== "object" || Array.isArray(body)) {
      return json({ error: "Body must be a JSON object" }, 400);
    }

    const result = validate(body as Record<string, unknown>);
    if ("errors" in result) {
      return json({ error: result.errors.join("; ") }, 400);
    }

    try {
      const base44 = createClientFromRequest(req);
      const created = await base44.asServiceRole.entities.SensorReading.create(
        result.reading,
      );
      return json({ ok: true, id: created?.id ?? null }, 201);
    } catch (err) {
      console.error("Failed to create SensorReading:", err);
      return json({ error: "Failed to store reading" }, 502);
    }
  } catch (err) {
    // Last-resort guard: never leak internals, always answer with JSON.
    console.error("push-sensor-reading crashed:", err);
    return json({ error: "Internal error" }, 500);
  }
}
