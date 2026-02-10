import { Brain, AlertTriangle, BookOpen } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfidenceBadge } from "@/components/shared/confidence-badge";

import { formatRelativeTime } from "@/lib/utils";

import type { AIEstimate } from "@/lib/types";

export function AIReasoning({ estimate }: { estimate: AIEstimate }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Brain className="h-5 w-5 text-primary" />
            AI Analysis
          </CardTitle>
          <ConfidenceBadge confidence={estimate.confidence} />
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <div>
          <p className="text-sm leading-relaxed text-foreground-muted whitespace-pre-wrap">
            {estimate.reasoning}
          </p>
        </div>

        {estimate.key_evidence.length > 0 && (
          <div>
            <h4 className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-widest text-foreground-muted">
              <BookOpen className="h-3.5 w-3.5" />
              Key Evidence
            </h4>
            <ul className="space-y-1.5">
              {estimate.key_evidence.map((evidence, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 text-sm text-foreground-muted"
                >
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                  {evidence}
                </li>
              ))}
            </ul>
          </div>
        )}

        {estimate.key_uncertainties.length > 0 && (
          <div>
            <h4 className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-widest text-foreground-muted">
              <AlertTriangle className="h-3.5 w-3.5" />
              Key Uncertainties
            </h4>
            <ul className="space-y-1.5">
              {estimate.key_uncertainties.map((uncertainty, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 text-sm text-foreground-muted"
                >
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ev-moderate" style={{ backgroundColor: "var(--ev-moderate)" }} />
                  {uncertainty}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="border-t border-border pt-4">
          <div className="flex items-center justify-between text-xs text-foreground-subtle">
            <span>Model: {estimate.model_used}</span>
            <span>{formatRelativeTime(estimate.created_at)}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
