import { useCallback, useEffect, useRef, useState } from "react";
import { Clapperboard, Film, History, Loader2, Plus, Sparkles, Trash2, Upload, X } from "lucide-react";
import { Job, Project, api, errText } from "../services/api";
import StatusChip from "../components/editor/StatusChip";
import { fmt } from "../utils/format";

export default function Dashboard({ onOpen }: { onOpen: (id: string) => void }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [history, setHistory] = useState<(Job & { project_name: string })[]>([]);
  const [show, setShow] = useState(false);
  const [health, setHealth] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const ps = await api.listProjects(); setProjects(ps);
      const js = await Promise.all(ps.slice(0, 12).map((p) => api.jobs(p.project_id).then((j) => j.map((x) => ({ ...x, project_name: p.project_name })))));
      setHistory(js.flat().filter((j) => j.kind === "final").sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 8));
    } catch (e) { setErr(errText(e)); }
  }, []);
  useEffect(() => { load(); api.health().then(setHealth).catch(() => setHealth(null)); }, [load]);

  return (
    <div className="min-h-full bg-[radial-gradient(ellipse_at_top,#1b1340_0%,#07080c_55%)]">
      <header className="max-w-6xl mx-auto px-6 pt-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-accent to-fuchsia-500 grid place-items-center shadow-lg shadow-accent/30"><Clapperboard size={22} /></div>
          <div><div className="text-xl font-bold tracking-tight">ClipGenius <span className="text-accent-soft">AI</span></div>
            <div className="text-xs text-slate-500">Intelligent agent-based video editing</div></div>
        </div>
        <button className="btn-primary" onClick={() => setShow(true)}><Plus size={16} /> New project</button>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-10 grid lg:grid-cols-[1fr_320px] gap-8">
        <section>
          <h2 className="text-2xl font-semibold mb-1">Edit video with an AI agent</h2>
          <p className="text-slate-400 text-sm mb-6 max-w-xl">Upload footage, describe the edit in plain language, review the plan the agent builds — scene scoring, A* sequencing, constraint checks — then render.</p>
          {err && <div className="panel p-3 text-rose-300 text-sm mb-4">{err} — is the backend running on port 8000?</div>}
          <div className="label mb-3">Recent projects</div>
          {projects.length === 0 ? (
            <button onClick={() => setShow(true)} className="panel w-full py-14 grid place-items-center text-slate-400 hover:border-accent/60 transition">
              <Upload size={28} className="mb-2 text-accent-soft" /><span>Upload your first video</span></button>
          ) : (
            <div className="grid sm:grid-cols-2 gap-4">
              {projects.map((p) => (
                <div key={p.project_id} className="panel p-4 hover:border-accent/60 transition cursor-pointer group" onClick={() => onOpen(p.project_id)}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0"><Film size={16} className="text-accent-soft shrink-0" /><div className="font-medium truncate">{p.project_name}</div></div>
                    <StatusChip status={p.status} />
                  </div>
                  <div className="text-xs text-slate-500 mt-2 truncate">{p.original_filename ?? "No video yet"}</div>
                  <div className="flex items-center gap-3 mt-3 text-xs text-slate-400">
                    <span>{p.duration ? fmt(p.duration) : "—"}</span>
                    {p.metadata && <span>{p.metadata.width}×{p.metadata.height}</span>}
                    {p.analysis_summary && <span>{p.analysis_summary.scene_count} scenes</span>}
                    <button className="ml-auto opacity-0 group-hover:opacity-100 text-rose-400 hover:text-rose-300" title="Delete project"
                      onClick={async (e) => { e.stopPropagation(); if (confirm(`Delete "${p.project_name}" and its files?`)) { await api.deleteProject(p.project_id); load(); } }}><Trash2 size={14} /></button>
                  </div>
                  {p.status === "analyzing" && <div className="h-1 bg-ink-700 rounded mt-3"><div className="h-1 bg-accent rounded" style={{ width: `${p.progress * 100}%` }} /></div>}
                </div>
              ))}
            </div>
          )}
        </section>
        <aside className="space-y-4">
          <div className="panel p-4">
            <div className="flex items-center gap-2 label mb-3"><History size={14} /> Editing history</div>
            {history.length === 0 ? <div className="text-sm text-slate-500">No exports yet.</div> : history.map((j) => (
              <div key={j.job_id} className="flex items-center justify-between py-1.5 text-sm border-b border-ink-700 last:border-0">
                <div className="truncate pr-2"><div className="truncate">{j.project_name}</div><div className="text-[11px] text-slate-500">{new Date(j.created_at).toLocaleString()}</div></div>
                {j.download_url ? <a className="text-accent-soft text-xs hover:underline" href={j.download_url}>Download</a> : <StatusChip status={j.status} />}
              </div>))}
          </div>
          <div className="panel p-4 text-xs text-slate-400 space-y-1.5">
            <div className="label mb-1">System</div>
            {health ? (<>
              <Row k="FFmpeg" ok={health.ffmpeg} /><Row k="FFprobe" ok={health.ffprobe} /><Row k={`Whisper (${health.whisper_model})`} ok={null} note="loads on first analysis" />
              <Row k="Gujarati subtitle font" ok={health.gujarati_font} /><Row k="LLM prompt parsing" ok={health.llm_configured} note="optional; local parser otherwise" /></>) : <div>Backend unreachable</div>}
          </div>
        </aside>
      </main>
      {show && <NewProject onClose={() => setShow(false)} onCreated={(id) => { setShow(false); onOpen(id); }} />}
    </div>
  );
}

const Row = ({ k, ok, note }: { k: string; ok: boolean | null; note?: string }) => (
  <div className="flex justify-between"><span>{k}</span><span className={ok === null ? "text-slate-500" : ok ? "text-lime-400" : "text-amber-400"}>{ok === null ? note : ok ? "ready" : note ?? "missing"}</span></div>);

function NewProject({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [prog, setProg] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const inp = useRef<HTMLInputElement>(null);
  const go = async () => {
    if (!file) return;
    setBusy(true); setErr(null);
    try {
      const p = await api.createProject(name.trim() || file.name.replace(/\.[^.]+$/, ""));
      try { await api.upload(p.project_id, file, setProg); } catch (e) { await api.deleteProject(p.project_id); throw e; }
      await api.analyze(p.project_id);
      onCreated(p.project_id);
    } catch (e) { setErr(errText(e)); setBusy(false); }
  };
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm grid place-items-center z-50 p-4">
      <div className="panel w-full max-w-md p-5">
        <div className="flex items-center justify-between mb-4"><div className="font-semibold">New project</div><button onClick={onClose}><X size={18} /></button></div>
        <label className="label">Project name</label>
        <input className="input mt-1 mb-4" placeholder="e.g. Product launch talk" value={name} onChange={(e) => setName(e.target.value)} />
        <div onClick={() => inp.current?.click()} onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); setFile(e.dataTransfer.files[0] ?? null); }}
          className="border border-dashed border-ink-500 hover:border-accent rounded-xl py-8 grid place-items-center cursor-pointer text-sm text-slate-400">
          <Upload className="mb-2 text-accent-soft" />{file ? <span className="text-slate-200">{file.name} · {(file.size / 1e6).toFixed(1)} MB</span> : "Drop a video or click to browse (mp4, mov, mkv, webm, avi)"}
        </div>
        <input ref={inp} type="file" accept="video/*,.mkv" hidden onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        {busy && <div className="h-1.5 bg-ink-700 rounded mt-4"><div className="h-1.5 bg-accent rounded transition-all" style={{ width: `${Math.max(3, prog * 100)}%` }} /></div>}
        {err && <div className="text-rose-300 text-sm mt-3">{err}</div>}
        <button className="btn-primary w-full mt-5" disabled={!file || busy} onClick={go}>{busy ? <><Loader2 className="animate-spin" size={16} /> Uploading…</> : <><Sparkles size={16} /> Upload & analyze</>}</button>
      </div>
    </div>
  );
}
