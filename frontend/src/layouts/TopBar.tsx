import { ArrowLeft, Clapperboard, Download, Eye, Save, Undo2, Redo2 } from "lucide-react";
import { useProject } from "../context/ProjectContext";
import StatusChip from "../components/editor/StatusChip";

export default function TopBar({ onHome, onExport, onPreview }: { onHome: () => void; onExport: () => void; onPreview: () => void }) {
  const { project, plan, refresh } = useProject();
  return (
    <div className="h-12 flex items-center gap-3 px-3 bg-ink-900 border-b border-ink-600/60">
      <button className="btn-ghost !px-2" onClick={onHome} title="Back to dashboard"><ArrowLeft size={16} /></button>
      <div className="flex items-center gap-2"><div className="w-6 h-6 rounded-md bg-gradient-to-br from-accent to-fuchsia-500 grid place-items-center"><Clapperboard size={14} /></div>
        <div className="font-semibold text-sm truncate max-w-[280px]">{project?.project_name ?? "…"}</div>{project && <StatusChip status={project.status} />}</div>
      <div className="flex items-center gap-1 ml-4 opacity-50" title="Edits are plan-based: re-plan to change. Undo/redo is not applicable to generated plans.">
        <button className="btn-ghost !px-2" disabled><Undo2 size={14} /></button><button className="btn-ghost !px-2" disabled><Redo2 size={14} /></button></div>
      <div className="ml-auto flex items-center gap-2">
        {project && project.status === "analyzing" && <div className="text-xs text-amber-300">{project.stage} · {Math.round(project.progress * 100)}%</div>}
        <button className="btn-ghost" onClick={refresh} title="Plans and analysis are saved automatically in the database"><Save size={14} /> Saved</button>
        <button className="btn-ghost" disabled={!plan?.renderable} onClick={onPreview}><Eye size={14} /> Preview</button>
        <button className="btn-primary" disabled={!plan?.renderable} onClick={onExport}><Download size={14} /> Export</button>
      </div>
    </div>
  );
}
