export function emailExpiry(expirySeconds: number): string {
  if (!Number.isSafeInteger(expirySeconds) || expirySeconds <= 0) throw new Error("Invalid email expiry");
  if (expirySeconds % 3600 === 0) {
    const hours = expirySeconds / 3600;
    return `${hours} ${hours === 1 ? "hora" : "horas"}`;
  }
  if (expirySeconds % 60 === 0) {
    const minutes = expirySeconds / 60;
    return `${minutes} ${minutes === 1 ? "minuto" : "minutos"}`;
  }
  return `${expirySeconds} ${expirySeconds === 1 ? "segundo" : "segundos"}`;
}
