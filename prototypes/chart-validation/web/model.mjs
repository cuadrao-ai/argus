// Rendering transforms only: no financial arithmetic or inferred values.
export function segments(points, key) {
  const result = [];
  let current = [];
  for (const point of points) {
    if (point[key] === null) {
      if (current.length) result.push(current);
      current = [];
    } else current.push({ time: point.time, value: point[key] });
  }
  if (current.length) result.push(current);
  return result;
}
export function nearestIndex(logical, count) {
  if (!count || logical === null) return null;
  // The library positions civil-date samples on a logical index axis.
  return Math.max(0, Math.min(count - 1, Math.ceil(logical - 0.5)));
}
export function formattedDate(time, locale) {
  return new Intl.DateTimeFormat(locale === 'en' ? 'en-US' : 'es-419', {
    year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC',
  }).format(new Date(`${time}T00:00:00Z`));
}
export function formattedValue(value, currency, locale) {
  if (value === null) return locale === 'en' ? 'No data' : 'Sin datos';
  return new Intl.NumberFormat(locale === 'en' ? 'en-US' : 'es-419', {
    style: 'currency', currency, currencyDisplay: 'code', minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(value);
}
