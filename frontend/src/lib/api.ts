import type { DocumentRecord, PreviewResponse, QueryResponse, SourceCitation } from "./types";

const baseUrl = "/api/zkb";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${baseUrl}${path}`, {...init, headers, cache: "no-store"});
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail ?? `HTTP ${response.status}`);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  documents: () => request<DocumentRecord[]>("/documents"),
  ingest: (file: File) => { const body = new FormData(); body.append("file", file); return request<{document:DocumentRecord}>("/ingest", {method:"POST", body}); },
  ingestUrl: (url: string) => request<{document:DocumentRecord}>("/ingest/url", {method:"POST", body:JSON.stringify({url})}),
  preview: (file: File) => { const body = new FormData(); body.append("file", file); return request<PreviewResponse>("/ingest/preview", {method:"POST", body}); },
  remove: (id: string) => request<void>(`/documents/${id}`, {method:"DELETE"}),
  reindex: (id: string) => request<{document:DocumentRecord}>(`/documents/${id}/reindex`, {method:"POST"}),
  ask: (question: string, top_k=5) => request<QueryResponse>("/query", {method:"POST", body:JSON.stringify({question, top_k, stream:false})}),
  search: (query: string, top_k=5) => request<{results:SourceCitation[]}>("/search", {method:"POST", body:JSON.stringify({query, top_k})}),
};
