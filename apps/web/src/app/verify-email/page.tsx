import Link from "next/link";

import * as authApi from "@/lib/api/auth";
import { AuthCard } from "@/components/AuthCard";
import { FormMessage } from "@/components/FormMessage";
import { link } from "@/lib/ui";
import { ResendVerificationForm } from "./ResendVerificationForm";

export default async function VerifyEmailPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;

  if (!token) {
    return (
      <AuthCard title="Verify your email">
        <p className="mb-4 text-sm text-muted-foreground">
          No verification token was provided. If your link expired, request
          a new one below.
        </p>
        <ResendVerificationForm />
      </AuthCard>
    );
  }

  const result = await authApi.verifyEmail(token);

  return (
    <AuthCard title="Verify your email">
      {result.ok ? (
        <div className="flex flex-col gap-4">
          <FormMessage message="Your email is verified." tone="success" />
          <Link href="/login" className={link}>
            Sign in
          </Link>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <FormMessage message={result.message} />
          <ResendVerificationForm />
        </div>
      )}
    </AuthCard>
  );
}
