import { NextRequest } from "next/server";

const backend = process.env.ZKB_BACKEND_URL ?? "http://backend:8000";
const apiKey = process.env.ZKB_API_KEY;

async function proxy(request: NextRequest, context: {params: {path: string[]}}) {
  if (!apiKey) return Response.json({detail:"Admin proxy is not configured"}, {status:503});
  const target = `${backend}/api/v1/${context.params.path.join("/")}${request.nextUrl.search}`;
  const headers = new Headers();
  headers.set("X-API-Key", apiKey);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const body = ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer();
  const upstream = await fetch(target, {method:request.method, headers, body, cache:"no-store", redirect:"manual"});
  const responseHeaders = new Headers();
  const upstreamType = upstream.headers.get("content-type");
  if (upstreamType) responseHeaders.set("content-type", upstreamType);
  return new Response(upstream.body, {status:upstream.status, headers:responseHeaders});
}

export const GET = proxy;
export const POST = proxy;
export const DELETE = proxy;
