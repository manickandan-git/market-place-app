// Shared Tailwind class strings so every form/button/card in the app draws
// from one small set of styles instead of ad-hoc classes per component.

export const input =
  "w-full rounded-lg border border-border bg-card px-3.5 py-2.5 text-sm text-foreground placeholder:text-muted-foreground shadow-sm transition-colors focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring/30";

export const label = "text-sm font-medium text-foreground";

export const select = input + " appearance-none bg-no-repeat";

const buttonBase =
  "inline-flex items-center justify-center gap-2 rounded-full px-5 py-2.5 text-sm font-medium transition-all disabled:cursor-not-allowed disabled:opacity-50";

export const buttonPrimary =
  buttonBase +
  " bg-primary text-primary-foreground shadow-sm hover:bg-primary-hover hover:shadow-md active:scale-[0.98]";

export const buttonSecondary =
  buttonBase +
  " border border-border bg-card text-foreground hover:bg-muted active:scale-[0.98]";

export const buttonDanger =
  buttonBase +
  " border border-danger/30 text-danger hover:bg-danger/10 active:scale-[0.98]";

export const buttonSmall = (variant: "primary" | "secondary" | "danger" = "secondary") =>
  (variant === "primary" ? buttonPrimary : variant === "danger" ? buttonDanger : buttonSecondary) +
  " !px-3.5 !py-1.5 text-xs";

export const link =
  "font-medium text-primary underline-offset-4 hover:underline";

export const card =
  "rounded-2xl border border-border bg-card p-6 shadow-sm";

export const badge =
  "inline-flex items-center rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-foreground";
