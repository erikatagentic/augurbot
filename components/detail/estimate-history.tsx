import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfidenceBadge } from "@/components/shared/confidence-badge";

import { formatPercent, formatRelativeTime } from "@/lib/utils";

import type { AIEstimate } from "@/lib/types";

export function EstimateHistory({ estimates }: { estimates: AIEstimate[] }) {
  if (!estimates.length) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Estimate History</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-foreground-muted">
            No estimates recorded yet.
          </p>
        </CardContent>
      </Card>
    );
  }

  const sorted = [...estimates].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Estimate History</CardTitle>
      </CardHeader>
      <CardContent>
        <Accordion type="single" collapsible className="w-full">
          {sorted.map((estimate, index) => (
            <AccordionItem key={estimate.id} value={estimate.id}>
              <AccordionTrigger className="hover:no-underline">
                <div className="flex flex-1 items-center gap-4">
                  <span className="text-2xl font-semibold tabular-nums">
                    {formatPercent(estimate.probability)}
                  </span>
                  <ConfidenceBadge confidence={estimate.confidence} />
                  <span className="text-xs text-foreground-subtle">
                    {estimate.model_used}
                  </span>
                  <span className="ml-auto text-xs text-foreground-muted">
                    {formatRelativeTime(estimate.created_at)}
                  </span>
                  {index === 0 && (
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                      Latest
                    </span>
                  )}
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <div className="space-y-3 pt-2">
                  <p className="text-sm leading-relaxed text-foreground-muted whitespace-pre-wrap">
                    {estimate.reasoning}
                  </p>

                  {estimate.key_evidence.length > 0 && (
                    <div>
                      <h5 className="mb-1 text-xs font-medium uppercase tracking-widest text-foreground-subtle">
                        Evidence
                      </h5>
                      <ul className="space-y-1">
                        {estimate.key_evidence.map((ev, i) => (
                          <li
                            key={i}
                            className="flex items-start gap-2 text-xs text-foreground-muted"
                          >
                            <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-primary" />
                            {ev}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {estimate.key_uncertainties.length > 0 && (
                    <div>
                      <h5 className="mb-1 text-xs font-medium uppercase tracking-widest text-foreground-subtle">
                        Uncertainties
                      </h5>
                      <ul className="space-y-1">
                        {estimate.key_uncertainties.map((u, i) => (
                          <li
                            key={i}
                            className="flex items-start gap-2 text-xs text-foreground-muted"
                          >
                            <span
                              className="mt-1 h-1 w-1 shrink-0 rounded-full"
                              style={{ backgroundColor: "var(--ev-moderate)" }}
                            />
                            {u}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </CardContent>
    </Card>
  );
}
