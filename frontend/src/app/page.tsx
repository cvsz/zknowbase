"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { DocumentRecord } from "@/lib/types";

export default function Dashboard() {
  const [docs,setDocs]=useState<DocumentRecord[]>([]); const [error,setError]=useState("");
  useEffect(()=>{api.documents().then(setDocs).catch(e=>setError(String(e)))},[]);
  const ready=docs.filter(d=>d.status==="ready").length; const chunks=docs.reduce((n,d)=>n+d.chunk_count,0);
  return <section className="space-y-8"><div><h1 className="text-3xl font-semibold">Knowledge Operations</h1><p className="mt-2 text-slate-400">Corpus health and retrieval readiness.</p></div>
    {error && <p className="rounded border border-red-900 bg-red-950/50 p-3 text-red-300">{error}</p>}
    <div className="grid gap-4 md:grid-cols-3">{[["Documents",docs.length],["Ready",ready],["Vector chunks",chunks]].map(([k,v])=><div key={String(k)} className="rounded-xl border border-slate-800 bg-slate-900 p-5"><div className="text-sm text-slate-400">{k}</div><div className="mt-2 text-3xl font-semibold">{v}</div></div>)}</div>
    <div className="rounded-xl border border-slate-800 bg-slate-900"><div className="border-b border-slate-800 p-4 font-medium">Recent documents</div><div className="divide-y divide-slate-800">{docs.slice(0,8).map(d=><div key={d.id} className="flex items-center justify-between p-4"><div><div>{d.name}</div><div className="text-xs text-slate-500">{d.chunk_count} chunks · {d.source_type}</div></div><span className="rounded-full bg-slate-800 px-3 py-1 text-xs">{d.status}</span></div>)}</div></div>
  </section>;
}
