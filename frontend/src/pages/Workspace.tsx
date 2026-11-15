import { useState } from "react";
import { BarChart3, Loader2, MonitorPlay, Wand2, Upload as UploadIcon, X } from "lucide-react";
import { ProjectProvider, useProject } from "../context/ProjectContext";
import TopBar from "../layouts/TopBar";
import MediaSidebar from "../components/editor/MediaSidebar";
import VideoPreview from "../components/preview/VideoPreview";
import Timeline from "../components/timeline/Timeline";
import Assistant from "../components/ai-assistant/Assistant";
import ExportPanel from "../components/export/ExportPanel";
import AnalysisDashboard from "../components/analysis/AnalysisDashboard";

function Inner({ onHome }: { onHome: () => void }) {
  const { project, error, setError, startPreview } = useProject();
  const [center, setCenter] = useState<"preview" | "analysis">("preview");
  const [right, setRight] = useState<"assistant" | "export">("assistant");
  const analyzing = project?.status === "analyzing" || (project?.status === "uploaded");
  return (
    <div className="h-full grid grid-rows-[48px_1fr_272px] grid-cols-[240px_1fr_390px] bg-ink-950">
      <div className="col-span-3"><TopBar onHome={onHome} onExport={() => setRight("export")} onPreview={async () => { setRight("export"); await startPreview(); }} /></div>
      <div className="row-start-2 min-h-0"><MediaSidebar /></div>
      <div className="row-start-2 min-h-0 min-w-0 flex flex-col">
        <div className="flex gap-1 px-3 pt-2">
          {([["preview", "Preview", MonitorPlay], ["analysis", "Analysis dashboard", BarChart3]] as const).map(([k, l, Icon]) => (
            <button key={k} onClick={() => setCenter(k)} className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg ${center === k ? "bg-ink-700 text-white" : "text-slate-500 hover:text-slate-300"}`}><Icon size={14} />{l}</button>))}
        </div>
        <div className="flex-1 min-h-0 relative">
          {center === "preview" ? <VideoPreview /> : <AnalysisDashboard />}
          {analyzing && (
            <div className="absolute inset-0 bg-ink-950/80 backdrop-blur-sm grid place-items-center z-30">
              <div className="panel p-6 w-80 text-center"><Loader2 className="animate-spin mx-auto text-accent-soft mb-3" />
                <div className="font-medium">{project?.stage || "Starting analysis"}</div>
                <div className="h-1.5 bg-ink-700 rounded mt-3"><div className="h-1.5 bg-gradient-to-r from-accent to-fuchsia-500 rounded transition-all" style={{ width: `${Math.max(4, (project?.progress ?? 0) * 100)}%` }} /></div>
                <div className="text-xs text-slate-500 mt-2">{Math.round((project?.progress ?? 0) * 100)}% — measured progress from the backend</div></div></div>)}
        </div>
      </div>
      <div className="row-start-2 min-h-0 bg-ink-900 border-l border-ink-600/60 flex flex-col">
        <div className="flex text-xs border-b border-ink-700">
          {([["assistant", "AI assistant", Wand2], ["export", "Export", UploadIcon]] as const).map(([k, l, Icon]) => (
            <button key={k} onClick={() => setRight(k)} className={`flex-1 py-2.5 flex items-center justify-center gap-1.5 font-semibold ${right === k ? "text-accent-soft border-b-2 border-accent" : "text-slate-500"}`}><Icon size={14} />{l}</button>))}
        </div>
        <div className="flex-1 min-h-0">{right === "assistant" ? <Assistant onApply={() => setRight("export")} /> : <ExportPanel />}</div>
      </div>
      <div className="col-span-3 row-start-3 min-h-0"><Timeline /></div>
      {error && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 panel border-rose-500/50 px-4 py-2.5 text-sm text-rose-200 flex items-start gap-3 max-w-xl shadow-2xl">
          <span className="break-words">{error}</span><button onClick={() => setError(null)}><X size={16} /></button></div>)}
    </div>
  );
}

export default function Workspace({ projectId, onHome }: { projectId: string; onHome: () => void }) {
  return <ProjectProvider projectId={projectId}><Inner onHome={onHome} /></ProjectProvider>;
}
