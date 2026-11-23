/**
 * Timestamp formatting shared by the journal list and the event detail.
 *
 * The backend stores UTC. These helpers render in the DEVICE's timezone,
 * which is what an operator needs ("was that at 3am?"), while the absolute
 * UTC value stays available on the detail screen so a reading can be matched
 * against a server log.
 */

/** Short form for a list row: "15 Jun, 14:03:22". */
export function formatTimestamp(value: string | null): string {
  if (!value) {
    return 'Unknown time';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/** Full form for the detail screen, including the year and the weekday. */
export function formatTimestampLong(value: string | null): string {
  if (!value) {
    return 'Unknown time';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(undefined, {
    weekday: 'long',
    day: '2-digit',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/**
 * "4 minutes ago". Shown next to the absolute time, never instead of it.
 *
 * A relative time alone would be useless in a thesis screenshot and
 * ambiguous in an audit trail, so it is only ever an addition.
 */
export function formatRelative(value: string | null): string | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  const seconds = Math.round((Date.now() - parsed.getTime()) / 1000);
  if (seconds < 0) {
    // A timestamp in the future means the device clock and the hub disagree.
    // Saying so is more useful than rendering "in 3 minutes".
    return 'clock ahead of this device';
  }
  if (seconds < 60) {
    return 'just now';
  }
  const units: [number, string][] = [
    [60, 'minute'],
    [60, 'hour'],
    [24, 'day'],
  ];
  let amount = seconds;
  let label = 'second';
  for (const [factor, nextLabel] of units) {
    if (amount < factor) {
      break;
    }
    amount = Math.floor(amount / factor);
    label = nextLabel;
  }
  return `${amount} ${label}${amount === 1 ? '' : 's'} ago`;
}
