export function formatRnc(value: string): string {
  const digits = value.replace(/\D/g, "");
  if (digits.length === 9) return `${digits.slice(0, 1)}-${digits.slice(1, 3)}-${digits.slice(3, 8)}-${digits.slice(8)}`;
  if (digits.length === 11) return `${digits.slice(0, 3)}-${digits.slice(3, 10)}-${digits.slice(10)}`;
  return value;
}
