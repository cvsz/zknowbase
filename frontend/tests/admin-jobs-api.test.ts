import assert from "node:assert/strict";
import test from "node:test";

import { api } from "../src/lib/api.ts";

test("admin jobs API uses the same-origin proxy", async () => {
  const calls: string[] = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: string | URL | Request) => {
    calls.push(String(input));
    return Response.json([]);
  }) as typeof fetch;

  try {
    const jobs = await api.ingestionJobs(25);

    assert.deepEqual(jobs, []);
    assert.deepEqual(calls, ["/api/zkb/ingest/jobs?limit=25"]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
