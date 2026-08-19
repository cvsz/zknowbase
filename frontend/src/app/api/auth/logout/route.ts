import { NextRequest, NextResponse } from "next/server";
import { ADMIN_SESSION_COOKIE, cookieSecure, sameOrigin } from "@/lib/admin-auth";

export function POST(request: NextRequest) {
  if (!sameOrigin(request.headers)) return Response.json({ detail: "Origin rejected" }, { status: 403 });
  const response = NextResponse.json({ ok: true });
  response.cookies.set(ADMIN_SESSION_COOKIE, "", {
    httpOnly: true,
    sameSite: "strict",
    secure: cookieSecure(),
    path: "/",
    maxAge: 0,
  });
  return response;
}
