import { NextRequest, NextResponse } from "next/server";
import {
  ADMIN_SESSION_COOKIE,
  cookieSecure,
  createAdminSession,
} from "@/lib/admin-auth";
import {
  OIDC_STATE_COOKIE,
  decodeStateCookie,
  exchangeAndLoadUser,
  oidcConfig,
} from "@/lib/oidc";

export async function GET(request: NextRequest) {
  const response = NextResponse.redirect(new URL("/", request.url));
  response.cookies.delete(OIDC_STATE_COOKIE);

  const code = request.nextUrl.searchParams.get("code") ?? "";
  const state = request.nextUrl.searchParams.get("state") ?? "";
  const saved = decodeStateCookie(request.cookies.get(OIDC_STATE_COOKIE)?.value);
  if (!code || code.length > 8192 || !saved || state !== saved.state) {
    return new Response("OIDC callback rejected", { status: 400 });
  }

  try {
    const config = oidcConfig();
    if (!config) return new Response("OIDC login is not configured", { status: 404 });
    if (new URL(config.redirectUri).origin !== request.nextUrl.origin) {
      throw new Error("ZKB_OIDC_REDIRECT_URI must use the Admin UI origin");
    }
    const user = await exchangeAndLoadUser(code, saved.verifier, config);
    response.cookies.set(
      ADMIN_SESSION_COOKIE,
      createAdminSession(user.subject, user.role, Math.floor(Date.now() / 1000), "oidc"),
      {
        httpOnly: true,
        sameSite: "strict",
        secure: cookieSecure(),
        path: "/",
        maxAge: 8 * 60 * 60,
      },
    );
    return response;
  } catch (error) {
    console.error("oidc_callback_failed", error);
    return new Response("OIDC authentication failed", { status: 403 });
  }
}
