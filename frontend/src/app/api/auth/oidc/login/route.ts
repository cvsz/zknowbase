import { NextRequest, NextResponse } from "next/server";
import { cookieSecure, sameOrigin } from "@/lib/admin-auth";
import {
  OIDC_STATE_COOKIE,
  discover,
  encodeStateCookie,
  newAuthorizationState,
  oidcConfig,
} from "@/lib/oidc";

export async function GET(request: NextRequest) {
  if (!sameOrigin(request.headers)) {
    return Response.json({ detail: "Origin rejected" }, { status: 403 });
  }
  try {
    const config = oidcConfig();
    if (!config) return Response.json({ detail: "OIDC login is not configured" }, { status: 404 });
    if (new URL(config.redirectUri).origin !== request.nextUrl.origin) {
      throw new Error("ZKB_OIDC_REDIRECT_URI must use the Admin UI origin");
    }
    const discovery = await discover(config);
    const { state, verifier, challenge } = newAuthorizationState();
    const target = new URL(discovery.authorization_endpoint);
    target.searchParams.set("client_id", config.clientId);
    target.searchParams.set("redirect_uri", config.redirectUri);
    target.searchParams.set("response_type", "code");
    target.searchParams.set("scope", "openid profile email");
    target.searchParams.set("state", state);
    target.searchParams.set("code_challenge", challenge);
    target.searchParams.set("code_challenge_method", "S256");

    const response = NextResponse.redirect(target);
    response.cookies.set(OIDC_STATE_COOKIE, encodeStateCookie(state, verifier), {
      httpOnly: true,
      sameSite: "lax",
      secure: cookieSecure(),
      path: "/api/auth/oidc",
      maxAge: 10 * 60,
    });
    return response;
  } catch (error) {
    console.error("oidc_authorization_start_failed", error);
    return Response.json({ detail: "OIDC authentication is not available" }, { status: 503 });
  }
}
