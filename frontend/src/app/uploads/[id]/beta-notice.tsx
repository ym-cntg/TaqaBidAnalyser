import { AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";

/** Shown anywhere an uploaded BOQ is visible, including the analysis
 *  tabs it feeds. The warning is specific rather than generic: a vague
 *  "this is beta" tells an analyst nothing about what might actually go
 *  wrong with the numbers in front of them. */
export function BetaBadge() {
  return (
    <Badge variant="secondary" className="bg-amber-500/15 text-amber-700 font-semibold">
      BETA
    </Badge>
  );
}

export function BetaNotice({ compact = false }: { compact?: boolean }) {
  return (
    <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-800">
      <p className="flex items-center gap-2 font-semibold">
        <AlertTriangle className="h-4 w-4" />
        Excel upload is under active testing and development
      </p>
      {!compact && (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
          <li>
            Check every extracted figure before confirming. Extraction is accurate on the
            standard templates but is not guaranteed on a spreadsheet it has not seen.
          </li>
          <li>
            Lines are matched across vendors by BOQ item number. A vendor who renumbered or
            removed that column may produce duplicate lines rather than matched ones.
          </li>
          <li>
            Uploaded BOQs are held in the running application and are lost if it restarts.
            Do not treat this as a record of anything.
          </li>
          <li>Use the Maximo path for any evaluation that counts.</li>
        </ul>
      )}
    </div>
  );
}
