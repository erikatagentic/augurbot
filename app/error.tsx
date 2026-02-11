"use client";

import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="flex max-w-md flex-col items-center text-center px-6">
        <AlertTriangle className="mb-4 h-12 w-12 text-ev-negative" />
        <h2 className="text-lg font-semibold">Something went wrong</h2>
        <p className="mt-2 text-sm text-foreground-muted">
          {error.message || "An unexpected error occurred."}
        </p>
        <Button onClick={reset} variant="outline" className="mt-6">
          Try again
        </Button>
      </div>
    </div>
  );
}
