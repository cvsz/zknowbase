"use client";
import { FormEvent, useState } from "react";
import { Send } from "lucide-react";
import { api } from "@/lib/api";
import type { QueryResponse } from "@/lib/types";

export default function Playground(){
 const [q,setQ]=useState(""),[result,setResult]=useState<QueryResponse|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState("");
 async function submit(e:FormEvent){e.preventDefault();if(!q.trim())return;setBusy(true);setError("");try{setResult(await api.ask(q,6))}catch(e){setError(String(e))}finally{setBusy(false)}}
 return <section className="space-y-6"><div><h1 className="text-3xl font-semibold">RAG Playground</h1><p className="mt-2 text-slate-400">Test grounded answers and inspect retrieved evidence.</p></div>
 <form onSubmit={submit} className="flex gap-2"><textarea rows={3} value={q} onChange={e=>setQ(e.target.value)} placeholder="Ask about a company policy or workflow…" className="flex-1 rounded-xl border border-slate-700 bg-slate-900 p-4"/><button disabled={busy} className="self-end rounded-lg bg-indigo-500 p-3"><Send size={18}/></button></form>
 {error&&<p className="text-red-300">{error}</p>}{result&&<><div className="rounded-xl border border-slate-800 bg-slate-900 p-5"><h2 className="mb-3 font-medium">Answer</h2><div className="whitespace-pre-wrap text-slate-200">{result.answer}</div></div><div><h2 className="mb-3 font-medium">Retrieved evidence</h2><div className="space-y-3">{result.sources.map((s,i)=><div key={s.chunk_id} className="rounded-xl border border-slate-800 bg-slate-900 p-4"><div className="mb-2 flex items-center justify-between text-xs text-slate-400"><span>[S{i+1}] {s.document_name} · chunk {s.chunk_index}</span><span>{(s.score*100).toFixed(1)}% relevance</span></div><div className="h-1.5 overflow-hidden rounded bg-slate-800"><div className="h-full bg-indigo-500" style={{width:`${Math.max(0,Math.min(100,s.score*100))}%`}}/></div><p className="mt-3 text-sm text-slate-300">{s.text}</p></div>)}</div></div></>}
 </section>
}
