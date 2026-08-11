export function FormMessage({
  message,
  tone = "error",
}: {
  message?: string;
  tone?: "error" | "success";
}) {
  if (!message) {
    return null;
  }
  return (
    <p
      className={
        tone === "error"
          ? "rounded-lg border border-danger/20 bg-danger/10 px-3.5 py-2.5 text-sm text-danger"
          : "rounded-lg border border-success/20 bg-success/10 px-3.5 py-2.5 text-sm text-success"
      }
    >
      {message}
    </p>
  );
}

export function FieldError({ message }: { message?: string }) {
  if (!message) {
    return null;
  }
  return <p className="text-xs text-danger">{message}</p>;
}
