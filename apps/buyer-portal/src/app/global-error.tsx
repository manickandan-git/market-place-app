"use client";

// Only triggers if the root layout itself throws. Per Next.js docs this
// replaces the entire document and does NOT include globals.css (our
// --color-primary etc. custom properties won't be defined), so this uses
// Tailwind's built-in default palette only, not our design tokens.
export default function GlobalError({
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <html lang="en">
      <body className="flex min-h-screen items-center justify-center bg-zinc-50 p-8">
        <div className="flex max-w-sm flex-col items-center gap-4 text-center">
          <h1 className="text-2xl font-semibold text-zinc-900">
            Something went wrong
          </h1>
          <p className="text-sm text-zinc-600">
            The app failed to load. Please try again.
          </p>
          <button
            onClick={() => retry()}
            className="rounded-full bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
