export function AuthCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto flex max-w-sm flex-col gap-6 py-8 sm:py-16">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle ? (
          <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
        ) : null}
      </div>
      <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
        {children}
      </div>
    </div>
  );
}
