import { NextResponse } from "next/server";
import { COOKIE_NAME, GATE_TTL_MS, mintGateCookie, secretsEqual } from "@/lib/gate";
import { clientKey, isLocked, rateLimit } from "@/lib/rate-limit";

const APP_SECRET = process.env.APP_SECRET;

// Failed-guess budget. Shared by the lockout check and the counter so they cannot drift.
const FAIL_LIMIT = 5;
const FAIL_WINDOW_MS = 15 * 60_000;

export const revalidate = 0;

function tooMany(retryAfterSec: number) {
  return new NextResponse("Too many attempts", {
    status: 429,
    headers: { "Retry-After": String(retryAfterSec) },
  });
}

/**
 * Exchange the server-only APP_SECRET for an httpOnly gate cookie.
 * The secret never needs to be embedded in client JS (no NEXT_PUBLIC_*).
 */
export async function POST(request: Request) {
  if (!APP_SECRET) {
    return NextResponse.json({ ok: true, gated: false });
  }

  const ip = clientKey(request);
  // Cap overall POSTs and failed guesses so short access codes cannot be brute-forced.
  const overall = rateLimit(`gate:all:${ip}`, { limit: 30, windowMs: 60_000 });
  if (!overall.ok) return tooMany(overall.retryAfterSec);

  // Enforce the failed-guess lockout before comparing, not inside the mismatch branch.
  // Checking it only on a wrong guess never blocks a right one, so an attacker who has
  // burned the budget keeps guessing: wrong answers 429 but a correct answer still mints
  // a cookie — the lockout would stop nothing it exists to stop.
  const failKey = `gate:fail:${ip}`;
  const locked = isLocked(failKey, FAIL_LIMIT);
  if (locked) return tooMany(locked.retryAfterSec);

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return new NextResponse("Invalid JSON", { status: 400 });
  }

  const secret =
    body && typeof body === "object" && "secret" in body && typeof (body as { secret: unknown }).secret === "string"
      ? (body as { secret: string }).secret
      : "";

  if (!secretsEqual(secret, APP_SECRET)) {
    // Only wrong guesses spend the budget; the check above rejects everything once spent.
    rateLimit(failKey, { limit: FAIL_LIMIT, windowMs: FAIL_WINDOW_MS });
    return new NextResponse("Unauthorized", { status: 401 });
  }

  const res = NextResponse.json({ ok: true, gated: true });
  res.cookies.set(COOKIE_NAME, mintGateCookie(APP_SECRET), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: Math.floor(GATE_TTL_MS / 1000),
  });
  return res;
}
