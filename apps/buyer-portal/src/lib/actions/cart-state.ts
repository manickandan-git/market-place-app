// See auth-state.ts for why this lives outside cart.ts: a "use server"
// file may only export async functions.

export interface CartActionState {
  ok: boolean;
  message?: string;
}

export const initialCartActionState: CartActionState = { ok: true };
