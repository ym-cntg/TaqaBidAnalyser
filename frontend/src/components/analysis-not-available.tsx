import { AlertTriangle } from "lucide-react";
import type { Project } from "@/lib/api";

export function AnalysisNotAvailable({ project }: { project: Project | null }) {
  return (
    <div className="p-8">
      <div className="flex items-start gap-3 rounded-xl border border-amber-400/40 bg-amber-500/5 px-4 py-4 max-w-2xl">
        <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5 shrink-0" />
        <div>
          <p className="font-medium">Not available for this project yet</p>
          <p className="text-sm text-muted-foreground mt-1">
            {project?.name ?? "This project"}&apos;s BOQ format hasn&apos;t been mapped to the
            extraction pipeline, so comparison, template building, insights, and reporting can&apos;t
            run yet. Document selection still works — see PROGRESS.md for what &quot;analysis
            ready&quot; depends on.
          </p>
        </div>
      </div>
    </div>
  );
}
