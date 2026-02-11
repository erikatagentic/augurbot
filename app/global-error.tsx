"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased">
        <div className="flex min-h-screen items-center justify-center bg-background text-foreground">
          <div className="flex max-w-md flex-col items-center text-center px-6">
            <h2 className="text-lg font-semibold">Something went wrong</h2>
            <p className="mt-2 text-sm text-neutral-400">
              {error.message || "An unexpected error occurred."}
            </p>
            <button
              onClick={reset}
              className="mt-6 rounded-md border border-neutral-700 px-4 py-2 text-sm hover:bg-neutral-800"
            >
              Try again
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
