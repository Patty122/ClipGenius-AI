import { useEffect, useState } from "react";
import Dashboard from "./pages/Dashboard";
import Workspace from "./pages/Workspace";

const parse = () => { const m = window.location.hash.match(/^#\/p\/([a-f0-9]+)/); return m ? m[1] : null; };

export default function App() {
  const [pid, setPid] = useState<string | null>(parse());
  useEffect(() => { const h = () => setPid(parse()); window.addEventListener("hashchange", h); return () => window.removeEventListener("hashchange", h); }, []);
  const open = (id: string | null) => { window.location.hash = id ? `#/p/${id}` : ""; setPid(id); };
  return pid ? <Workspace projectId={pid} onHome={() => open(null)} /> : <Dashboard onOpen={open} />;
}
