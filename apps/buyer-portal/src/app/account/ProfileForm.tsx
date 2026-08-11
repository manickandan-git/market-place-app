"use client";

import { useActionState } from "react";

import { FieldError, FormMessage } from "@/components/FormMessage";
import { createProfileAction, updateProfileAction } from "@/lib/actions/profile";
import type { Profile } from "@/lib/api/profile";
import { buttonPrimary, card, input, label as labelClass } from "@/lib/ui";

const initialState = { ok: true as const };

export function ProfileForm({ profile }: { profile: Profile | null }) {
  const action = profile ? updateProfileAction : createProfileAction;
  const [state, formAction, pending] = useActionState(action, initialState);

  return (
    <form action={formAction} className={card + " flex max-w-sm flex-col gap-4"}>
      {profile ? (
        <input type="hidden" name="version" value={profile.version} />
      ) : null}

      <FormMessage message={state.ok ? undefined : state.message} />
      {state.ok && state.message ? (
        <FormMessage message={state.message} tone="success" />
      ) : null}

      {!profile ? (
        <p className="text-sm text-muted-foreground">
          You don&apos;t have a marketplace profile yet — create one to save
          addresses and preferences.
        </p>
      ) : null}

      <div className="flex flex-col gap-1.5">
        <label htmlFor="display_name" className={labelClass}>
          Display name
        </label>
        <input
          id="display_name"
          name="display_name"
          required
          defaultValue={profile?.display_name ?? ""}
          className={input}
        />
        <FieldError message={state.fieldErrors?.display_name} />
      </div>

      {profile ? (
        <>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="first_name" className={labelClass}>
              First name
            </label>
            <input
              id="first_name"
              name="first_name"
              defaultValue={profile.first_name ?? ""}
              className={input}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="last_name" className={labelClass}>
              Last name
            </label>
            <input
              id="last_name"
              name="last_name"
              defaultValue={profile.last_name ?? ""}
              className={input}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="phone_number" className={labelClass}>
              Phone
            </label>
            <input
              id="phone_number"
              name="phone_number"
              defaultValue={profile.phone_number ?? ""}
              className={input}
            />
          </div>
        </>
      ) : null}

      <button
        type="submit"
        disabled={pending}
        className={buttonPrimary + " self-start"}
      >
        {pending ? "Saving…" : profile ? "Save changes" : "Create profile"}
      </button>
    </form>
  );
}
