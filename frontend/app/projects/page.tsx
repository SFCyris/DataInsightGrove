import { redirect } from "next/navigation";

// DIG's unit of work is the Pipeline, not a separate "Project" container.
// The /projects route used to render a "Phase 1+" placeholder; nothing in
// the app links to it, so a direct URL hit (old bookmark, typed path)
// should land on the real workspace rather than a dead-end message.
// Server-side redirect → /pipelines (307; replace, so back-button skips it).
export default function ProjectsPage() {
  redirect("/pipelines");
}
