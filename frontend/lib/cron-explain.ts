/**
 * Minimal, dependency-free cron explainer. Produces a one-line plain-
 * English description for the common shapes (5-field cron: m h dom mon dow).
 * Returns ``null`` for inputs the heuristics can't summarise — caller can
 * then show the raw expression instead.
 *
 * Round-6 UX#4 finding: the schedules page asked users to type cron with
 * only the canonical "m h dom mon dow" hint above the input. Even seasoned
 * ops folks pause to mentally parse "30 14 * * 1-5". This helper covers the
 * 90 % cases (every / at / weekly / specific time) so the user gets a
 * confidence-checking readback below the input.
 */

const DAY_NAMES: Record<string, string> = {
  "0": "Sunday", "1": "Monday", "2": "Tuesday", "3": "Wednesday",
  "4": "Thursday", "5": "Friday", "6": "Saturday", "7": "Sunday",
};

const MONTH_NAMES: Record<string, string> = {
  "1": "January", "2": "February", "3": "March", "4": "April",
  "5": "May", "6": "June", "7": "July", "8": "August", "9": "September",
  "10": "October", "11": "November", "12": "December",
};

function pad2(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

function describeTime(min: string, hr: string): string {
  if (min === "*" && hr === "*") return "every minute";
  if (min === "0" && hr === "*") return "at the top of every hour";
  if (min === "*" && /^\d+$/.test(hr)) return `every minute of hour ${hr}`;
  if (/^\d+$/.test(min) && /^\d+$/.test(hr)) {
    return `at ${pad2(+hr)}:${pad2(+min)}`;
  }
  if (min.startsWith("*/")) {
    const step = min.slice(2);
    return `every ${step} minutes`;
  }
  if (hr.startsWith("*/")) {
    const step = hr.slice(2);
    return `every ${step} hours at :${pad2(+min || 0)}`;
  }
  return `m=${min}, h=${hr}`;
}

function describeDow(dow: string): string | null {
  if (dow === "*") return null;
  if (/^\d$/.test(dow)) return `on ${DAY_NAMES[dow]}`;
  if (dow === "1-5") return "on weekdays";
  if (dow === "0,6" || dow === "6,0" || dow === "0-0,6-6") return "on weekends";
  const parts = dow.split(",").map((s) => s.trim());
  if (parts.every((p) => /^\d$/.test(p))) {
    return "on " + parts.map((p) => DAY_NAMES[p]).join(", ");
  }
  return null;
}

function describeDomMon(dom: string, mon: string): string | null {
  const parts: string[] = [];
  if (mon !== "*" && /^\d+$/.test(mon)) parts.push(`in ${MONTH_NAMES[mon]}`);
  if (dom !== "*" && /^\d+$/.test(dom)) parts.push(`on the ${dom}${ordSuffix(+dom)}`);
  return parts.length > 0 ? parts.join(" ") : null;
}

function ordSuffix(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return s[(v - 20) % 10] ?? s[v] ?? s[0];
}

export function explainCron(expr: string): string | null {
  const fields = expr.trim().split(/\s+/);
  if (fields.length !== 5) return null;
  const [min, hr, dom, mon, dow] = fields;
  const time = describeTime(min, hr);
  const dowDesc = describeDow(dow);
  const dateDesc = describeDomMon(dom, mon);
  const everyday = dow === "*" && dom === "*" && mon === "*";
  const parts: string[] = [time];
  if (dowDesc) parts.push(dowDesc);
  if (dateDesc) parts.push(dateDesc);
  if (everyday && !dowDesc) parts.push("every day");
  return parts.join(", ");
}

/**
 * Compute the next firing time of a 5-field cron expression at-or-after
 * ``from``. Returns null when the schedule never fires within the next
 * year (defensive) or the expression can't be parsed.
 *
 * Not a perfect implementation of every cron quirk (no L/W/# /Q
 * specials, no list-of-ranges) — just the common shapes the schedules
 * page wants to preview. For the impossible-day backend rejection
 * already gates anything obviously broken, so this is best-effort UX.
 */
export function nextFireTime(expr: string, from: Date = new Date()): Date | null {
  const fields = expr.trim().split(/\s+/);
  if (fields.length !== 5) return null;
  const [minS, hrS, domS, monS, dowS] = fields;
  const exp = (s: string, lo: number, hi: number): Set<number> => {
    const out = new Set<number>();
    if (s === "*") {
      for (let i = lo; i <= hi; i++) out.add(i);
      return out;
    }
    for (const tok of s.split(",")) {
      let step = 1;
      let base = tok;
      if (tok.includes("/")) {
        const [b, st] = tok.split("/");
        step = parseInt(st, 10) || 1;
        base = b;
      }
      let from2 = lo, to = hi;
      if (base === "*") {
        from2 = lo; to = hi;
      } else if (base.includes("-")) {
        const [a, b] = base.split("-").map((x) => parseInt(x, 10));
        if (Number.isNaN(a) || Number.isNaN(b)) return new Set();
        from2 = a; to = b;
      } else {
        const v = parseInt(base, 10);
        if (Number.isNaN(v)) return new Set();
        from2 = v; to = v;
      }
      for (let i = from2; i <= to; i += step) {
        if (i >= lo && i <= hi) out.add(i);
      }
    }
    return out;
  };
  const minSet = exp(minS, 0, 59);
  const hrSet  = exp(hrS, 0, 23);
  const domSet = exp(domS, 1, 31);
  const monSet = exp(monS, 1, 12);
  const dowSet = exp(dowS, 0, 7);
  if (dowSet.has(7)) dowSet.add(0); // 7 == Sun
  if (
    !minSet.size || !hrSet.size || !domSet.size || !monSet.size || !dowSet.size
  ) return null;

  // Try the next 366 days, minute-by-day search.
  const start = new Date(from.getTime());
  start.setSeconds(0, 0);
  start.setMinutes(start.getMinutes() + 1);
  for (let d = 0; d < 366; d++) {
    const day = new Date(start.getTime() + d * 86_400_000);
    if (!monSet.has(day.getMonth() + 1)) continue;
    if (!domSet.has(day.getDate())) continue;
    if (!dowSet.has(day.getDay())) continue;
    // Walk every (hr, min) in order, but only after `start` on the first
    // candidate day.
    const startMs = d === 0 ? start.getTime() : 0;
    for (const h of [...hrSet].sort((a, b) => a - b)) {
      for (const m of [...minSet].sort((a, b) => a - b)) {
        const c = new Date(day);
        c.setHours(h, m, 0, 0);
        if (c.getTime() >= startMs) return c;
      }
    }
  }
  return null;
}

export function describeRelative(target: Date, from: Date = new Date()): string {
  const ms = target.getTime() - from.getTime();
  if (ms <= 0) return "now";
  if (ms < 60_000) return "in <1 min";
  if (ms < 3_600_000) return `in ${Math.round(ms / 60_000)} min`;
  if (ms < 86_400_000) {
    const h = Math.floor(ms / 3_600_000);
    const m = Math.round((ms % 3_600_000) / 60_000);
    return m > 0 ? `in ${h}h ${m}m` : `in ${h}h`;
  }
  const days = Math.round(ms / 86_400_000);
  return `in ${days}d`;
}
