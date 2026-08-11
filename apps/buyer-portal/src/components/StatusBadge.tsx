const TONE_CLASSES: Record<"neutral" | "primary" | "success" | "warning" | "danger", string> = {
  neutral: "bg-muted text-muted-foreground",
  primary: "bg-primary/10 text-primary",
  success: "bg-success/10 text-success",
  warning: "bg-accent/15 text-accent",
  danger: "bg-danger/10 text-danger",
};

const ORDER_STATUS_TONE: Record<string, keyof typeof TONE_CLASSES> = {
  pending_payment: "warning",
  payment_authorized: "primary",
  confirmed: "primary",
  processing: "primary",
  shipped: "primary",
  delivered: "success",
  cancelled: "neutral",
  payment_failed: "danger",
};

function label(value: string): string {
  return value.replace(/_/g, " ");
}

export function StatusBadge({ status }: { status: string }) {
  const tone = ORDER_STATUS_TONE[status] ?? "neutral";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium capitalize ${TONE_CLASSES[tone]}`}
    >
      {label(status)}
    </span>
  );
}
