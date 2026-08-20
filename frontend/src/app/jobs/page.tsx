"use client";
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Clock3, Loader2, RotateCcw, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import type { IngestionJobRecord } from "@/lib/types";

const statuses = ["queued", "processing", "failed", "completed", "cancelled"] as const;

function formatTime(value?: string | null) {
  if (!value) return "none";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function statusClass(status: IngestionJobRecord["status"]) {
  if (status === "failed") return "border-red-800 bg-red-950/60 text-red-200";
  if (status === "processing") return "border-sky-800 bg-sky-950/50 text-sky-200";
  if (status === "queued") return "border-amber-800 bg-amber-950/50 text-amber-200";
  if (status === "cancelled") return "border-slate-700 bg-slate-900 text-slate-300";
  return "border-emerald-800 bg-emerald-950/50 text-emerald-200";
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<IngestionJobRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try {
      setJobs(await api.ingestionJobs(100));
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const counts = useMemo(() => {
    return Object.fromEntries(statuses.map(status => [
      status,
      jobs.filter(job => job.status === status).length,
    ])) as Record<IngestionJobRecord["status"], number>;
  }, [jobs]);

  const retryPressure = jobs.filter(job => job.status !== "completed" && job.attempts > 0).length;

  return <section className="space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-3xl font-semibold">Ingestion jobs</h1>
        <p className="mt-2 text-slate-400">Tenant-scoped queue health, retries, worker leases, and source provenance.</p>
      </div>
      <button onClick={() => { setLoading(true); void load(); }} className="inline-flex items-center gap-2 rounded border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800">
        <RotateCcw size={16} /> Refresh
      </button>
    </div>

    {error && <div className="flex items-center gap-2 rounded border border-red-900 bg-red-950/50 p-3 text-sm text-red-200"><AlertTriangle size={16} />{error}</div>}

    <div className="grid gap-3 md:grid-cols-6">
      {statuses.map(status => <div key={status} className="rounded-lg border border-slate-800 bg-slate-900 p-4">
        <div className="text-xs uppercase tracking-wide text-slate-500">{status}</div>
        <div className="mt-2 text-2xl font-semibold">{counts[status]}</div>
      </div>)}
      <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
        <div className="text-xs uppercase tracking-wide text-slate-500">retrying</div>
        <div className="mt-2 text-2xl font-semibold">{retryPressure}</div>
      </div>
    </div>

    <div className="overflow-hidden rounded-lg border border-slate-800">
      <table className="w-full table-fixed text-sm">
        <thead className="bg-slate-900 text-left text-slate-400">
          <tr>
            <th className="w-[24%] p-4">Job</th>
            <th className="w-[14%]">Status</th>
            <th className="w-[12%]">Attempts</th>
            <th className="w-[18%]">Lease</th>
            <th className="w-[18%]">Source</th>
            <th className="w-[14%] pr-4">Updated</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {loading && <tr><td colSpan={6} className="p-6 text-slate-400"><span className="inline-flex items-center gap-2"><Loader2 size={16} className="animate-spin" />Loading jobs</span></td></tr>}
          {!loading && jobs.length === 0 && <tr><td colSpan={6} className="p-6 text-slate-500">No ingestion jobs are currently recorded.</td></tr>}
          {!loading && jobs.map(job => <tr key={job.id} className="align-top">
            <td className="p-4">
              <div className="truncate font-medium">{job.document_id}</div>
              <div className="mt-1 truncate text-xs text-slate-500">{job.id}</div>
              {job.error && <div className="mt-2 flex gap-2 rounded border border-red-950 bg-red-950/40 p-2 text-xs text-red-200"><XCircle size={14} className="mt-0.5 shrink-0" /> <span className="max-h-14 overflow-hidden">{job.error}</span></div>}
            </td>
            <td><span className={`inline-flex rounded-full border px-2.5 py-1 text-xs ${statusClass(job.status)}`}>{job.status}</span></td>
            <td>{job.attempts}/{job.max_attempts}</td>
            <td className="pr-3 text-xs text-slate-400">
              <div className="flex items-center gap-1"><Clock3 size={13} />{formatTime(job.lease_expires_at)}</div>
              {job.worker_id && <div className="mt-1 truncate text-slate-500">{job.worker_id}</div>}
            </td>
            <td className="pr-3">
              <div>{job.source_type}</div>
              <div className="mt-1 truncate text-xs text-slate-500">{job.source_uri}</div>
            </td>
            <td className="pr-4 text-xs text-slate-400">{formatTime(job.updated_at)}</td>
          </tr>)}
        </tbody>
      </table>
    </div>
  </section>;
}
