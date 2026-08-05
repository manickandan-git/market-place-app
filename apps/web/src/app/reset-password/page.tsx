import Link from "next/link";

import { AuthCard } from "@/components/AuthCard";
import { link } from "@/lib/ui";
import { ResetPasswordForm } from "./ResetPasswordForm";

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;

  return (
    <AuthCard title="Set a new password">
      {token ? (
        <ResetPasswordForm token={token} />
      ) : (
        <p className="text-sm text-muted-foreground">
          This link is missing its reset token.{" "}
          <Link href="/forgot-password" className={link}>
            Request a new one
          </Link>
          .
        </p>
      )}
    </AuthCard>
  );
}
