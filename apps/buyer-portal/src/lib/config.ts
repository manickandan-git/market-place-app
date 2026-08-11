function requireEnv(name: string, fallback?: string): string {
  const value = process.env[name] ?? fallback;
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

export const config = {
  // Server-side only — the gateway is never called from the browser
  // directly (BFF pattern), so this never needs a NEXT_PUBLIC_ prefix.
  gatewayUrl: requireEnv("GATEWAY_URL", "http://localhost:9000"),
  // Publishable key is safe to expose to the browser by design (Stripe's
  // own convention) — it's the only Stripe credential the client needs,
  // used for stripe.confirmPayment(), never for charging anything.
  stripePublishableKey: process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY ?? "pk_test_51U0XLWPAO1Ix6BTP7RewIBZlKDKhGFzwdBEhEvCCgoNpIUIsJ4inTnJZXKJ6TM53fdu9I4jlWVdZAWdDfbMlPYDY00bDBNqxwR",
};
