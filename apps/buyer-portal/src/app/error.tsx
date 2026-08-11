"use client";

import { buttonPrimary } from "@/lib/ui";

export default function Error({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <div className="mx-auto flex max-w-sm flex-col items-start gap-4 py-16 text-center sm:items-center">
      <h1 className="text-2xl font-semibold">Something went wrong</h1>
      <p className="text-sm text-muted-foreground">
        {error.digest
          ? `We hit a problem loading this page (ref: ${error.digest}).`
          : "We hit a problem loading this page."}
      </p>
      <button onClick={() => retry()} className={buttonPrimary}>
        Try again
      </button>
    </div>
  );
}
