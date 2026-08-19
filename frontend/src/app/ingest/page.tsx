"use client";
import { DragEvent, useState } from "react";
import { UploadCloud } from "lucide-react";
import { api } from "@/lib/api";
import type { PreviewResponse } from "@/lib/types";

export default function IngestPage(){
 const [file,setFile]=useState<File|null>(null),[preview,setPreview]=useState<PreviewResponse|null>(null),[url,setUrl]=useState(""),[message,setMessage]=useState("");
 async function choose(f:File){setFile(f);setMessage("");try{setPreview(await api.preview(f))}catch(e){setMessage(String(e))}}
 async function upload(){if(!file)return;setMessage("Uploading and indexing…");try{const r=await api.ingest(file);setMessage(`Indexed ${r.document.chunk_count} chunks`)}catch(e){setMessage(String(e))}}
 async function uploadUrl(){setMessage("Fetching and indexing URL…");try{const r=await api.ingestUrl(url);setMessage(`Indexed ${r.document.chunk_count} chunks`)}catch(e){setMessage(String(e))}}
 function drop(e:DragEvent){e.preventDefault();const f=e.dataTransfer.files[0];if(f)void choose(f)}
 return <section className="space-y-6"><div><h1 className="text-3xl font-semibold">Document ingestion</h1><p className="mt-2 text-slate-400">PDF, Markdown, text, or a public web URL.</p></div>
  <div onDragOver={e=>e.preventDefault()} onDrop={drop} className="rounded-xl border border-dashed border-slate-700 bg-slate-900 p-10 text-center"><UploadCloud className="mx-auto mb-3"/><p>Drop a document here</p><label className="mt-4 inline-block cursor-pointer rounded bg-white px-4 py-2 text-sm font-medium text-slate-950">Choose file<input className="hidden" type="file" accept=".pdf,.md,.markdown,.txt" onChange={e=>e.target.files?.[0]&&void choose(e.target.files[0])}/></label></div>
  {file&&<div className="rounded-xl border border-slate-800 bg-slate-900 p-5"><div className="flex justify-between"><div><b>{file.name}</b><p className="text-sm text-slate-400">{preview?.total_chunks ?? "…"} chunks</p></div><button onClick={()=>void upload()} className="rounded bg-indigo-500 px-4 py-2 text-sm">Index document</button></div>{preview&&<div className="mt-4 max-h-80 space-y-2 overflow-auto">{preview.chunks.slice(0,5).map(c=><pre key={c.index} className="whitespace-pre-wrap rounded bg-slate-950 p-3 text-xs text-slate-300">#{c.index} · {c.characters} chars\n{c.text}</pre>)}</div>}</div>}
  <div className="rounded-xl border border-slate-800 bg-slate-900 p-5"><h2 className="font-medium">Ingest public URL</h2><div className="mt-3 flex gap-2"><input value={url} onChange={e=>setUrl(e.target.value)} placeholder="https://example.com/policy" className="flex-1 rounded border border-slate-700 bg-slate-950 px-3 py-2"/><button disabled={!url} onClick={()=>void uploadUrl()} className="rounded bg-indigo-500 px-4 py-2 disabled:opacity-40">Index URL</button></div></div>
  {message&&<p className="text-sm text-slate-300">{message}</p>}
 </section>
}
