import { FileText, Film, Image, Music, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { useProject } from "../../context/ProjectContext";
import { api, errText, thumbUrl } from "../../services/api";
import { fmt } from "../../utils/format";

export default function MediaSidebar() {
  const { project, analysis, plan, seekTo, refresh, runAnalysis, setError } = useProject();
  const music = useRef<HTMLInputElement>(null);
  const srt = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<"media" | "files">("media");
  if (!project) return null;
  const upMusic = async (f?: File) => { if (!f) return; try { await api.uploadMusic(project.project_id, f); await refresh(); } catch (e) { setError(errText(e)); } };
  const upSrt = async (f?: File) => {
    if (!f) return;
    try { await api.importSrt(project.project_id, await f.text()); await runAnalysis(true); } catch (e) { setError(errText(e)); }
  };
  return (
    <div className="h-full bg-ink-900 border-r border-ink-600/60 flex flex-col min-h-0">
      <div className="flex text-xs border-b border-ink-700">
        {(["media", "files"] as const).map((t) => <button key={t} onClick={() => setTab(t)} className={`flex-1 py-2.5 font-semibold uppercase tracking-wider ${tab === t ? "text-accent-soft border-b-2 border-accent" : "text-slate-500"}`}>{t === "media" ? "Media" : "Project files"}</button>)}
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {tab === "media" ? (<>
          <div><div className="label mb-2 flex items-center gap-1.5"><Film size={12} /> Uploaded video</div>
            <div className="panel p-2.5 text-xs"><div className="font-medium truncate">{project.original_filename}</div>
              {project.metadata && <div className="text-slate-500 mt-1">{project.metadata.width}×{project.metadata.height} · {project.metadata.fps} fps · {fmt(project.metadata.duration)}<br />{project.metadata.video_codec}{project.metadata.audio_codec ? ` / ${project.metadata.audio_codec}` : " · no audio"}</div>}</div></div>
          <div><div className="label mb-2 flex items-center gap-1.5"><Music size={12} /> Audio assets</div>
            {project.has_music ? <div className="panel p-2.5 text-xs text-lime-300">Background music uploaded</div> : <div className="text-xs text-slate-500 mb-2">No music uploaded.</div>}
            <button className="btn-ghost w-full !text-xs" onClick={() => music.current?.click()}><Upload size={12} /> {project.has_music ? "Replace" : "Add"} music</button>
            <input ref={music} hidden type="file" accept="audio/*" onChange={(e) => upMusic(e.target.files?.[0])} /></div>
          <div><div className="label mb-2 flex items-center gap-1.5"><FileText size={12} /> Generated subtitles</div>
            {plan && plan.subtitles.cue_count > 0 ? <div className="panel p-2.5 text-xs"><div>{plan.subtitles.cue_count} cues · {plan.subtitles.style}</div>
              <a className="text-accent-soft hover:underline" href={`/api/edit/${project.project_id}/subtitles.srt`}>Download SRT</a></div>
              : <div className="text-xs text-slate-500">{analysis?.transcript.status === "ok" ? "Plan an edit to generate subtitles." : "No transcript available."}</div>}
            <button className="btn-ghost w-full !text-xs mt-2" onClick={() => srt.current?.click()}><Upload size={12} /> Import SRT transcript</button>
            <input ref={srt} hidden type="file" accept=".srt,text/plain" onChange={(e) => upSrt(e.target.files?.[0])} /></div>
        </>) : (<>
          <div className="label mb-2 flex items-center gap-1.5"><Image size={12} /> Scene thumbnails</div>
          <div className="grid grid-cols-2 gap-2">
            {analysis?.scenes.map((s) => {
              const sel = plan?.clips.some((c) => c.scene_id === s.scene_id);
              return (<button key={s.scene_id} onClick={() => seekTo(s.start)} className={`text-left rounded-lg overflow-hidden border ${sel ? "border-lime-400/70" : "border-ink-600"} hover:border-accent`}>
                <img src={thumbUrl(project.project_id, s.scene_id)} alt="" className="w-full aspect-video object-cover bg-ink-700" loading="lazy" />
                <div className="px-1.5 py-1 text-[10px] flex justify-between text-slate-400"><span>#{s.scene_id} · {fmt(s.start)}</span><span>{Math.round(s.importance)}</span></div></button>);
            }) ?? <div className="text-xs text-slate-500 col-span-2">Analysis not ready.</div>}
          </div></>)}
      </div>
    </div>
  );
}
