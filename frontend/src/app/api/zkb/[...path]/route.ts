import { NextRequest } from "next/server";
import {
  ADMIN_SESSION_COOKIE,
  canProxy,
  sameOrigin,
  verifyAdminSession,
} from "@/lib/admin-auth";

const backend = process.env.ZKB_BACKEND_URL ?? "http://backend:8000";
const apiKey = process.env.ZKB_API_KEY;

// Next.js 15 resolves dynamic route params asynchronously.
type RouteContext = {
  params: Promise<{ path: string[] }>;
};

async function proxy(request: NextRequest, context: RouteContext) {
  if (!apiKey) {
    return Response.json({ detail: "Admin proxy is not configured" }, { status: 503 });
  }

  let session = null;
  try {
    session = verifyAdminSession(request.cookies.get(ADMIN_SESSION_COOKIE)?.value);
  } catch {
    return Response.json(
      { detail: "Admin authentication is not configured" },
      { status: 503 },
    );
  }

  if (!session) {
    return Response.json({ detail: "Admin session required" }, { status: 401 });
  }

  const { path } = await context.params;

  if (!canProxy(session, request.method, path)) {
    return Response.json(
      { detail: "Admin role does not permit this operation" },
      { status: 403 },
    );
  }

  if (!["GET", "HEAD"].includes(request.method) && !sameOrigin(request.headers)) {
    return Response.json({ detail: "Origin rejected" }, { status: 403 });
  }

  const target = `${backend}/api/v1/${path.join("/")}${request.nextUrl.search}`;
  const headers = new Headers();
  headers.set("X-API-Key", apiKey);

  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);

  const requestId = request.headers.get("x-request-id");
  if (requestId) headers.set("x-request-id", requestId);

  const body = ["GET", "HEAD"].includes(request.method)
    ? undefined
    : await request.arrayBuffer();

  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body,
    cache: "no-store",
    redirect: "manual",
  });

  const responseHeaders = new Headers();
  const upstreamType = upstream.headers.get("content-type");
  if (upstreamType) responseHeaders.set("content-type", upstreamType);

  const upstreamRequestId = upstream.headers.get("x-request-id");
  if (upstreamRequestId) responseHeaders.set("x-request-id", upstreamRequestId);

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const DELETE = proxy;
