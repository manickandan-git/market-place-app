import Link from "next/link";

import { getCurrentUser } from "@/lib/api/identity";
import { getProfile } from "@/lib/api/profile";
import { card, link } from "@/lib/ui";
import { ProfileForm } from "./ProfileForm";

export default async function AccountPage() {
  const [user, profile] = await Promise.all([getCurrentUser(), getProfile()]);

  if (!user) {
    // proxy.ts already redirects unauthenticated requests to /login before
    // this ever renders; a null user here means the access token expired
    // in the few seconds between that check and this fetch (see proxy.ts's
    // docstring) — recoverable by simply reloading.
    return (
      <p className="text-sm text-muted-foreground">
        Your session expired. Please refresh the page.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-10">
      <h1 className="text-3xl font-semibold tracking-tight">Account</h1>

      <div className={card}>
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 text-sm">
          <dt className="text-muted-foreground">Name</dt>
          <dd>
            {user.first_name} {user.last_name}
          </dd>
          <dt className="text-muted-foreground">Email</dt>
          <dd>{user.email}</dd>
          <dt className="text-muted-foreground">Role</dt>
          <dd className="capitalize">{user.role.toLowerCase()}</dd>
          <dt className="text-muted-foreground">Email verified</dt>
          <dd>{user.is_email_verified ? "Yes" : "No"}</dd>
        </dl>
      </div>

      <div>
        <h2 className="mb-4 text-xl font-semibold">Profile</h2>
        <ProfileForm profile={profile} />
      </div>

      <div>
        <Link href="/account/addresses" className={link}>
          Manage addresses →
        </Link>
      </div>
    </div>
  );
}
