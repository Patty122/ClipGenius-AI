import { useState } from "react";
import { AlertTriangle, CheckCircle2, Download, Film, Loader2, Music, XCircle } from "lucide-react";
import { useProject } from "../../context/ProjectContext";
import { Job } from "../../services/api";
import StatusChip from "../editor/StatusChip";
import { fmt } from "../../utils/format";

export default function ExportPanel() {
  const { project, plan, jobs, startRender, startPreview } = useProject();
  const [o, setO] = useState({ quality: "", aspect_ratio: "", subtitles: true, music_enabled: false, normalize_audio: true, burn_subtitles: true });
  const [open, setOpen] = useState<string | null>(null);
  if (!project) return null;
  const go = (kind: "final" | "preview") => {
    if (kind === "preview") return startPreview();
    const opts: Record<string, any> = { subtitles: o.subtitles, normalize_audio: o.normalize_audio, burn_subtitles: o.burn_subtitles, music_enabled: o.music_enabled };
    if (o.quality) opts.quality = o.quality; if (o.aspect_ratio) opts.aspect_ratio = o.aspect_ratio;
    return startRender(opts);
  };
  const busy = jobs.some((j) => j.kind === "final" && (j.status === "running" || j.status === "queued"));
  return (
    <div className="h-full overflow-y-auto p-3 space-y-4">
      <div className="panel p-3 space-y-3">
        <div className="label">Export settings</div>
        {!plan?.renderable && <div className="text-xs text-amber-300 flex gap-1.5"><AlertTriangle size={13} className="shrink-0" />Create a valid editing plan in the AI assistant first — invalid plans are never rendered.</div>}
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div><div className="label mb-1">Resolution</div><select className="input !py-1" value={o.quality} onChange={(e) => setO({ ...o, quality: e.target.value })}><option value="">plan ({plan?.output.height ? `${plan.output.width}×${plan.output.height}` : "—"})</option><option value="1080p">1080p</option><option value="720p">720p</option></select></div>
          <div><div className="label mb-1">Aspect ratio</div><select className="input !py-1" value={o.aspect_ratio} onChange={(e) => setO({ ...o, aspect_ratio: e.target.value })}><option value="">plan ({plan?.output.aspect ?? "—"})</option><option>9:16</option><option>16:9</option><option>1:1</option></select></div>
          <div><div className="label mb-1">Format</div><select className="input !py-1" disabled><option>MP4 (H.264 + AAC)</option></select></div>
        </div>
        <div className="space-y-1.5 text-xs">
          <label className="flex items-center gap-2"><input type="checkbox" checked={o.subtitles} onChange={(e) => setO({ ...o, subtitles: e.target.checked })} /> Include subtitles</label>
          <label className="flex items-center gap-2 pl-5 text-slate-400"><input type="checkbox" disabled={!o.subtitles} checked={o.burn_subtitles} onChange={(e) => setO({ ...o, burn_subtitles: e.target.checked })} /> Burn into video (SRT is always saved separately)</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={o.normalize_audio} onChange={(e) => setO({ ...o, normalize_audio: e.target.checked })} /> Normalize loudness (EBU R128)</label>
          <label className="flex items-center gap-2"><input type="checkbox" disabled={!project.has_music} checked={o.music_enabled} onChange={(e) => setO({ ...o, music_enabled: e.target.checked })} /><Music size={12} /> Mix background music {project.has_music ? "(ducked under speech)" : "(upload music in Media panel)"}</label>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost flex-1" disabled={!plan?.renderable} onClick={() => go("preview")}>Quick preview</button>
          <button className="btn-primary flex-1" disabled={!plan?.renderable || busy} onClick={() => go("final")}>{busy ? <Loader2 size={14} className="animate-spin" /> : <Film size={14} />} Export MP4</button>
        </div>
        <div className="text-[11px] text-slate-500">Changing aspect/resolution re-plans automatically so the constraint solver validates the new configuration before rendering.</div>
      </div>
      <div className="label">Render jobs</div>
      {jobs.length === 0 && <div className="text-xs text-slate-500">No renders yet.</div>}
      {jobs.map((j) => <JobCard key={j.job_id} j={j} open={open === j.job_id} toggle={() => setOpen(open === j.job_id ? null : j.job_id)} />)}
    </div>);
}

function JobCard({ j, open, toggle }: { j: Job; open: boolean; toggle: () => void }) {
  const r = j.report;
  return (
    <div className="panel p-3 space-y-2">
      <div className="flex items-center justify-between"><div className="text-sm font-medium capitalize">{j.kind} render</div><StatusChip status={j.status} /></div>
      {(j.status === "running" || j.status === "queued") && (<><div className="h-2 bg-ink-700 rounded"><div className="h-2 rounded bg-gradient-to-r from-accent to-fuchsia-500 transition-all" style={{ width: `${Math.max(2, j.progress * 100)}%` }} /></div>
        <div className="text-xs text-slate-400">{j.stage} · {Math.round(j.progress * 100)}%</div></>)}
      {j.status === "failed" && <div className="text-xs text-rose-300 whitespace-pre-wrap break-words max-h-32 overflow-auto">{j.error_message}</div>}
      {j.status === "completed" && j.download_url && (<div className="flex items-center gap-2">
        <a className="btn-primary !text-xs" href={j.download_url} download><Download size={13} /> Download MP4</a>
        <button className="btn-ghost !text-xs" onClick={toggle}>{open ? "Hide" : "Execution"} report</button></div>)}
      {open && r && (
        <div className="text-[11px] space-y-1 bg-ink-900 rounded-lg p-2.5">
          <KV k="Original duration" v={fmt(r.original_duration, true)} /><KV k="Final duration (measured)" v={`${fmt(r.final_duration_measured, true)} (target ${r.target_duration}±${r.duration_tolerance})`} />
          <KV k="Scenes detected / selected" v={`${r.scenes_detected} / ${r.scenes_selected}`} /><KV k="Removed" v={`${r.removed_segments.scenes_removed} scenes, ${r.removed_segments.silence_intervals_trimmed} silence gaps (${r.removed_segments.silence_seconds_trimmed}s)`} />
          <KV k={`${r.astar.algorithm} nodes expanded/explored`} v={`${r.astar.nodes_expanded} / ${r.astar.states_explored}`} /><KV k="A* path cost vs chronological" v={`${r.astar.path_cost} vs ${r.astar.chronological_cost}`} />
          <KV k="CSP" v={`${r.csp.status}, ${r.csp.nodes} nodes, validation ${r.csp.independent_validation}`} /><KV k="Rules fired" v={r.expert_rules_triggered.join(", ")} />
          <KV k="Processing" v={`analysis ${r.processing_seconds.analysis}s · planning ${r.processing_seconds.planning}s · render ${r.processing_seconds.render}s`} />
          <div className="pt-1 border-t border-ink-700">{r.output_verification.checks.map((c: any) => <div key={c.check} className="flex items-center gap-1">{c.ok ? <CheckCircle2 size={11} className="text-lime-400" /> : <XCircle size={11} className="text-rose-400" />}{c.check}: <span className="text-slate-400">{c.detail}</span></div>)}</div>
        </div>)}
    </div>);
}
const KV = ({ k, v }: { k: string; v: string }) => <div className="flex justify-between gap-3"><span className="text-slate-500">{k}</span><span className="text-right">{v}</span></div>;
