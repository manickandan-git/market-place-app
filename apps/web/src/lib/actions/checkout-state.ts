// See auth-state.ts for why this lives outside checkout.ts: a "use server"
// file may only export async functions.

export interface CheckoutActionState {
  ok: boolean;
  message?: string;
  fieldErrors?: Record<string, string>;
}

export const initialCheckoutActionState: CheckoutActionState = { ok: true };
