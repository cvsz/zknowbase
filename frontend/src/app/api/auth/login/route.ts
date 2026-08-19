import { NextRequest, NextResponse } from "next/server";
import {
  ADMIN_SESSION_COOKIE,
  authenticateLocalUser,
  cookieSecure,
  createAdminSession,
  sameOrigin,
} from "@/lib/admin-auth";

const attempts = new Map<string, { count: number; resetAt: number }>();
const WINDOW_MS = 5 * 60 * 1000;
const MAX_ATTEMPTS = 8;

function clientKey(request: NextRequest): string {
  return request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "local";
}

function rateLimited(key: string): boolean {
  const now = Date.now();
  const current = attempts.get(key);
  if (!current || current.resetAt <= now) {
    attempts.set(key, { count: 0, resetAt: now + WINDOW_MS });
    return false;
  }
  return current.count >= MAX_ATTEMPTS;
}

function recordFailure(key: string): void {
  const now = Date.now();
  const current = attempts.get(key);
  if (!current || current.resetAt <= now) attempts.set(key, { count: 1, resetAt: now + WINDOW_MS });
  else current.count += 1;
}

export async function POST(request: NextRequest) {
  if (!sameOrigin(request.headers)) return Response.json({ detail: "Origin rejected" }, { status: 403 });
  const key = clientKey(request);
  if (rateLimited(key)) return Response.json({ detail: "Too many login attempts" }, { status: 429 });

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ detail: "Invalid JSON" }, { status: 400 });
  }
  if (!body || typeof body !== "object") return Response.json({ detail: "Invalid credentials" }, { status: 401 });
  const record = body as Record<string, unknown>;
  const username = typeof record.username === "string" ? record.username : "";
  const password = typeof record.password === "string" ? record.password : "";

  try {
    const user = authenticateLocalUser(username, password);
    if (!user) {
      recordFailure(key);
      return Response.json({ detail: "Invalid credentials" }, { status: 401 });
    }
    attempts.delete(key);
    const response = NextResponse.json({ username: user.username, role: user.role });
    response.cookies.set(ADMIN_SESSION_COOKIE, createAdminSession(user.username, user.role), {
      httpOnly: true,
      sameSite: "strict",
      secure: cookieSecure(),
      path: "/",
      maxAge: 8 * 60 * 60,
    });
    return response;
  } catch (error) {
    console.error("admin_auth_configuration_error", error);
    return Response.json({ detail: "Admin authentication is not configured" }, { status: 503 });
  }
}
