import { useEffect, useState } from "react";

/**
 * How long a page has left, in words.
 *
 * Stated everywhere the design can find room for it, because nothing survives
 * the hour and a visitor who does not know that will lose work. Rounded up and
 * kept vague on purpose — the exact second is not actionable, and a ticking
 * countdown would turn a generous hour into a deadline to watch.
 */
export function formatRemaining(expiresAt: Date, now: Date): string {
  const seconds = Math.round((expiresAt.getTime() - now.getTime()) / 1000);
  if (seconds <= 0) {
    return "any moment now";
  }
  const minutes = Math.ceil(seconds / 60);
  if (minutes === 1) {
    return "under a minute";
  }
  return `${minutes} minutes`;
}

/**
 * The current time, re-read every `intervalMs`.
 *
 * Half a minute, because what is shown is rounded to whole minutes: refreshing
 * faster would re-render for nothing, and slower would leave the last minute
 * reading "2 minutes" for a while after it was one.
 */
export function useNow(intervalMs = 30_000): Date {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);

  return now;
}
