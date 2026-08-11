export function formatPrice(amount: string | number, currency: string): string {
  const value = typeof amount === "number" ? amount : Number(amount);
  if (Number.isNaN(value)) {
    return `${amount} ${currency}`;
  }
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(
    value,
  );
}
