const SECONDS_PER_UNIT: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 60 * 60],
  ["month", 30 * 24 * 60 * 60],
  ["week", 7 * 24 * 60 * 60],
  ["day", 24 * 60 * 60],
  ["hour", 60 * 60],
  ["minute", 60],
];

const JUST_NOW = "just now";

const formatter = new Intl.RelativeTimeFormat(undefined, {
  numeric: "auto",
  style: "short",
});

export function relativeTime(isoTimestamp: string, now: number): string {
  const elapsedSeconds = Math.round((new Date(isoTimestamp).getTime() - now) / 1000);
  for (const [unit, seconds] of SECONDS_PER_UNIT) {
    if (Math.abs(elapsedSeconds) >= seconds) {
      return formatter.format(Math.round(elapsedSeconds / seconds), unit);
    }
  }
  return JUST_NOW;
}
