// Plain data, deliberately NOT in auth.ts: a "use server" file may only
// export async functions — a const object export breaks the build
// (confirmed by actually running `next dev`, see the commit history for
// the exact error). Client form components import the initial state from
// here and the action functions from ./auth.

export interface AuthActionState {
  ok: boolean;
  message?: string;
  fieldErrors?: Record<string, string>;
}

export const initialAuthActionState: AuthActionState = { ok: true };

export interface RegisterActionState extends AuthActionState {
  verificationToken?: string | null;
}
