"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "motion/react";

/**
 * Visual filter builder — no-SQL UI for the `filter_rows` step.
 *
 * Designed for beginners: pick a column → pick an operator → enter a value.
 * Multiple conditions joined by AND/OR. Outputs a SQL boolean predicate string
 * back into the `predicate` param. A "Show as SQL" toggle reveals the
 * generated SQL for power users; switching to SQL mode is one-way (the parser
 * doesn't try to round-trip arbitrary SQL back into structured conditions).
 */

type LogicalType = "string" | "integer" | "double" | "boolean" | "date" | "datetime" | "unknown";

interface Condition {
  column: string;
  op: string;
  value: string;
  value2?: string; // for "between"
}

interface Props {
  /** Available column names from the upstream step. */
  columns: string[];
  /** Optional column types so we can offer the right operators. */
  columnTypes?: Record<string, LogicalType>;
  /** Current SQL predicate string (the param value). */
  value: string;
  /** Called with a new SQL string. */
  onChange: (sql: string) => void;
}

const OPS_NUMERIC = [
  { id: "eq", label: "=" },
  { id: "neq", label: "≠" },
  { id: "gt", label: ">" },
  { id: "gte", label: "≥" },
  { id: "lt", label: "<" },
  { id: "lte", label: "≤" },
  { id: "between", label: "between" },
  { id: "is_null", label: "is empty" },
  { id: "is_not_null", label: "is not empty" },
];

const OPS_STRING = [
  { id: "eq", label: "is" },
  { id: "neq", label: "is not" },
  { id: "contains", label: "contains" },
  { id: "starts_with", label: "starts with" },
  { id: "ends_with", label: "ends with" },
  { id: "in_list", label: "in list" },
  { id: "is_null", label: "is empty" },
  { id: "is_not_null", label: "is not empty" },
];

const OPS_BOOLEAN = [
  { id: "eq", label: "is true", noValue: true, fixed: "true" },
  { id: "neq", label: "is false", noValue: true, fixed: "false" },
  { id: "is_null", label: "is empty" },
  { id: "is_not_null", label: "is not empty" },
];

const OPS_DATE = [
  { id: "eq", label: "on" },
  { id: "neq", label: "not on" },
  { id: "gt", label: "after" },
  { id: "gte", label: "on or after" },
  { id: "lt", label: "before" },
  { id: "lte", label: "on or before" },
  { id: "between", label: "between" },
  { id: "is_null", label: "is empty" },
  { id: "is_not_null", label: "is not empty" },
];

interface OpDef { id: string; label: string; noValue?: boolean; fixed?: string }

function opsForType(t: LogicalType): OpDef[] {
  switch (t) {
    case "integer":
    case "double":
      return OPS_NUMERIC;
    case "boolean":
      return OPS_BOOLEAN;
    case "date":
    case "datetime":
      return OPS_DATE;
    case "string":
    default:
      return OPS_STRING;
  }
}

function quoteIdent(s: string): string {
  return '"' + s.replace(/"/g, '""') + '"';
}
function quoteStr(s: string): string {
  return "'" + s.replace(/'/g, "''") + "'";
}
function literalForType(t: LogicalType, raw: string): string {
  if (raw === "" || raw == null) return "NULL";
  if (t === "integer" || t === "double") {
    const n = Number(raw);
    return Number.isFinite(n) ? String(n) : quoteStr(raw);
  }
  if (t === "boolean") {
    if (/^(true|1|yes|y)$/i.test(raw)) return "true";
    if (/^(false|0|no|n)$/i.test(raw)) return "false";
    return quoteStr(raw);
  }
  if (t === "date") return `DATE ${quoteStr(raw)}`;
  if (t === "datetime") return `TIMESTAMP ${quoteStr(raw)}`;
  return quoteStr(raw);
}

function condToSql(c: Condition, type: LogicalType): string {
  const col = quoteIdent(c.column);
  switch (c.op) {
    case "eq": return `${col} = ${literalForType(type, c.value)}`;
    case "neq": return `${col} <> ${literalForType(type, c.value)}`;
    case "gt": return `${col} > ${literalForType(type, c.value)}`;
    case "gte": return `${col} >= ${literalForType(type, c.value)}`;
    case "lt": return `${col} < ${literalForType(type, c.value)}`;
    case "lte": return `${col} <= ${literalForType(type, c.value)}`;
    case "between":
      return `${col} BETWEEN ${literalForType(type, c.value)} AND ${literalForType(type, c.value2 ?? "")}`;
    case "contains": return `${col} LIKE ${quoteStr("%" + c.value + "%")}`;
    case "starts_with": return `${col} LIKE ${quoteStr(c.value + "%")}`;
    case "ends_with": return `${col} LIKE ${quoteStr("%" + c.value)}`;
    case "in_list": {
      const items = c.value.split(",").map((s) => s.trim()).filter(Boolean);
      if (items.length === 0) return "TRUE";
      return `${col} IN (${items.map((v) => literalForType(type, v)).join(", ")})`;
    }
    case "is_null": return `${col} IS NULL`;
    case "is_not_null": return `${col} IS NOT NULL`;
    default: return "TRUE";
  }
}

function buildSql(conds: Condition[], joiner: "AND" | "OR", types: Record<string, LogicalType>): string {
  if (conds.length === 0) return "";
  const parts = conds
    .filter((c) => c.column)
    .map((c) => condToSql(c, types[c.column] ?? "string"));
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0];
  return parts.map((p) => `(${p})`).join(` ${joiner} `);
}

/** Best-effort parser: tries to recover a structured condition list from SQL
 *  the visual builder itself generates. Returns null if it can't parse — the
 *  caller falls back to raw-SQL mode so the value isn't mangled. */
function parseSql(
  sql: string,
): { conds: Condition[]; joiner: "AND" | "OR" } | null {
  const trimmed = sql.trim();
  if (!trimmed) return null;

  // Detect joiner. Top-level AND/OR with parenthesized parts is what buildSql
  // emits for ≥2 conditions; a single condition has no parens around it.
  const splitTop = (s: string, sep: "AND" | "OR"): string[] | null => {
    const parts: string[] = [];
    let depth = 0, start = 0;
    const re = new RegExp(`\\s${sep}\\s`, "i");
    for (let i = 0; i < s.length; i++) {
      const ch = s[i];
      if (ch === "(") depth++;
      else if (ch === ")") depth--;
      else if (depth === 0) {
        const sub = s.substring(i, i + sep.length + 2);
        if (re.test(" " + sub.toUpperCase().slice(0, sep.length + 2))) {
          // simpler: check sub matches " AND " / " OR "
        }
      }
    }
    // Simpler: regex-walk for top-level separator
    const out: string[] = [];
    let cur = "";
    let d = 0;
    let j = 0;
    while (j < s.length) {
      const ch = s[j];
      if (ch === "(") { d++; cur += ch; j++; continue; }
      if (ch === ")") { d--; cur += ch; j++; continue; }
      if (d === 0) {
        const tail = s.slice(j, j + sep.length + 2).toUpperCase();
        const want = ` ${sep} `;
        if (tail.startsWith(want)) {
          out.push(cur);
          cur = "";
          j += want.length;
          continue;
        }
      }
      cur += ch; j++;
    }
    out.push(cur);
    return out.length > 1 ? out : null;
  };

  let parts: string[] | null = null;
  let joiner: "AND" | "OR" = "AND";
  parts = splitTop(trimmed, "AND");
  if (!parts) {
    parts = splitTop(trimmed, "OR");
    if (parts) joiner = "OR";
  }
  if (!parts) parts = [trimmed];

  // Strip outer parens on each part.
  const stripped = parts.map((p) => {
    let t = p.trim();
    while (t.startsWith("(") && t.endsWith(")")) {
      // only strip if the parens are matching
      let d = 0, ok = true;
      for (let i = 0; i < t.length - 1; i++) {
        if (t[i] === "(") d++;
        else if (t[i] === ")") { d--; if (d === 0) { ok = false; break; } }
      }
      if (!ok) break;
      t = t.slice(1, -1).trim();
    }
    return t;
  });

  const conds: Condition[] = [];
  for (const p of stripped) {
    const c = parseOneCondition(p);
    if (!c) return null;
    conds.push(c);
  }
  return { conds, joiner };
}

function parseOneCondition(s: string): Condition | null {
  // Identifier: "col" or col
  const idRe = /^("([^"]|"")+"|[A-Za-z_][A-Za-z0-9_]*)\s*/;
  const m = s.match(idRe);
  if (!m) return null;
  const rawCol = m[1];
  const column = rawCol.startsWith('"')
    ? rawCol.slice(1, -1).replace(/""/g, '"')
    : rawCol;
  const rest = s.slice(m[0].length).trim();

  // IS NULL / IS NOT NULL
  if (/^IS\s+NULL$/i.test(rest)) return { column, op: "is_null", value: "" };
  if (/^IS\s+NOT\s+NULL$/i.test(rest)) return { column, op: "is_not_null", value: "" };

  // BETWEEN x AND y
  const btw = rest.match(/^BETWEEN\s+(.+?)\s+AND\s+(.+)$/i);
  if (btw) {
    return {
      column, op: "between",
      value: stripLiteral(btw[1]), value2: stripLiteral(btw[2]),
    };
  }

  // IN (a, b, c)
  const inM = rest.match(/^IN\s*\((.*)\)$/i);
  if (inM) {
    const items = splitCsv(inM[1]).map(stripLiteral);
    return { column, op: "in_list", value: items.join(", ") };
  }

  // LIKE 'pat'
  const likeM = rest.match(/^LIKE\s+(.+)$/i);
  if (likeM) {
    const lit = stripLiteral(likeM[1]);
    if (lit.startsWith("%") && lit.endsWith("%") && lit.length >= 2) {
      return { column, op: "contains", value: lit.slice(1, -1) };
    }
    if (lit.endsWith("%")) return { column, op: "starts_with", value: lit.slice(0, -1) };
    if (lit.startsWith("%")) return { column, op: "ends_with", value: lit.slice(1) };
    return { column, op: "eq", value: lit };
  }

  // OP literal — order matters: longer ops first
  for (const [pat, op] of [
    [/^<=\s*(.+)$/, "lte"],
    [/^>=\s*(.+)$/, "gte"],
    [/^<>\s*(.+)$/, "neq"],
    [/^!=\s*(.+)$/, "neq"],
    [/^<\s*(.+)$/,  "lt"],
    [/^>\s*(.+)$/,  "gt"],
    [/^=\s*(.+)$/,  "eq"],
  ] as const) {
    const m2 = rest.match(pat);
    if (m2) return { column, op, value: stripLiteral(m2[1]) };
  }

  return null;
}

function stripLiteral(s: string): string {
  const t = s.trim();
  if (/^(true|false)$/i.test(t)) return t.toLowerCase();
  if (/^-?\d+(\.\d+)?$/.test(t)) return t;
  if (/^DATE\s+'/i.test(t) || /^TIMESTAMP\s+'/i.test(t)) {
    return stripLiteral(t.replace(/^(DATE|TIMESTAMP)\s+/i, ""));
  }
  if (t.startsWith("'") && t.endsWith("'")) {
    return t.slice(1, -1).replace(/''/g, "'");
  }
  return t;
}

function splitCsv(s: string): string[] {
  const out: string[] = [];
  let cur = "", inStr = false;
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (ch === "'") {
      inStr = !inStr;
      cur += ch;
    } else if (ch === "," && !inStr) {
      out.push(cur);
      cur = "";
    } else cur += ch;
  }
  if (cur.trim()) out.push(cur);
  return out;
}

export function FilterBuilder({ columns, columnTypes = {}, value, onChange }: Props) {
  // Try to recover structured conditions from any incoming SQL. If we can't,
  // start in SQL mode so the predicate isn't silently overwritten on mount.
  const initial = useMemo(() => parseSql(value || ""), []);  // eslint-disable-line react-hooks/exhaustive-deps
  const [mode, setMode] = useState<"visual" | "sql">(() => {
    if (!value || !value.trim()) return "visual";
    return initial ? "visual" : "sql";
  });
  const [conds, setConds] = useState<Condition[]>(() => {
    if (initial && initial.conds.length > 0) return initial.conds;
    return [{ column: columns[0] ?? "", op: "eq", value: "" }];
  });
  const [joiner, setJoiner] = useState<"AND" | "OR">(initial?.joiner ?? "AND");

  const generatedSql = useMemo(
    () => buildSql(conds, joiner, columnTypes),
    [conds, joiner, columnTypes],
  );

  // Push generated SQL upward when in visual mode AND the user has actually
  // edited (i.e. the generated SQL differs from what we parsed-in). We never
  // overwrite an unparseable initial value — that path goes to SQL mode above.
  useEffect(() => {
    if (mode === "visual" && generatedSql && generatedSql !== value) {
      onChange(generatedSql);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generatedSql, mode]);

  const update = (idx: number, patch: Partial<Condition>) => {
    setConds((cs) => cs.map((c, i) => (i === idx ? { ...c, ...patch } : c)));
  };
  const addCond = () => {
    setConds((cs) => [
      ...cs,
      { column: columns[0] ?? "", op: "eq", value: "" },
    ]);
  };
  const removeCond = (idx: number) => {
    setConds((cs) => (cs.length === 1 ? cs : cs.filter((_, i) => i !== idx)));
  };

  if (columns.length === 0) {
    return (
      <p className="text-xs text-muted-foreground italic">
        Connect this step to data to see column choices.
      </p>
    );
  }

  if (mode === "sql") {
    return (
      <div className="space-y-2">
        <textarea
          className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm font-mono min-h-[80px] focus:outline-none focus:ring-2 focus:ring-ring/40"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="SQL boolean expression"
          spellCheck={false}
        />
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span>Raw SQL · WHERE clause</span>
          <button
            type="button"
            onClick={() => setMode("visual")}
            className="hover:text-foreground underline-offset-2 hover:underline"
          >
            ← back to visual
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <AnimatePresence initial={false} mode="popLayout">
        {conds.map((c, idx) => {
          const t = (columnTypes[c.column] ?? "string") as LogicalType;
          const ops = opsForType(t);
          const opDef = ops.find((o) => o.id === c.op) ?? ops[0];
          const noValue = "noValue" in opDef ? opDef.noValue : ["is_null", "is_not_null"].includes(opDef.id);
          return (
            <motion.div
              key={idx}
              layout
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.97 }}
              transition={{ type: "spring", stiffness: 320, damping: 28 }}
              className="rounded-md border border-border bg-card/40 p-1.5"
            >
              <div className="flex flex-wrap gap-1.5 items-center">
                {idx > 0 && (
                  <button
                    type="button"
                    role="switch"
                    aria-checked={joiner === "OR"}
                    aria-label={`Combine with ${joiner}; click to switch to ${joiner === "AND" ? "OR" : "AND"}`}
                    onClick={() => setJoiner((j) => (j === "AND" ? "OR" : "AND"))}
                    className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded border border-border hover:bg-muted"
                    title="Click to switch AND ↔ OR"
                  >
                    {joiner}
                  </button>
                )}
                <select
                  value={c.column}
                  onChange={(e) => update(idx, { column: e.target.value })}
                  className="rounded-md border border-input bg-background px-1.5 py-1 text-xs max-w-[120px]"
                >
                  {columns.map((col) => (
                    <option key={col} value={col}>{col}</option>
                  ))}
                </select>
                <select
                  value={c.op}
                  onChange={(e) => update(idx, { op: e.target.value })}
                  className="rounded-md border border-input bg-background px-1.5 py-1 text-xs"
                >
                  {ops.map((o) => (
                    <option key={o.id} value={o.id}>{o.label}</option>
                  ))}
                </select>
                {!noValue && c.op !== "between" && (
                  <input
                    type={t === "integer" || t === "double" ? "number" : t === "date" ? "date" : "text"}
                    value={c.value}
                    onChange={(e) => update(idx, { value: e.target.value })}
                    placeholder={c.op === "in_list" ? "a, b, c" : "value"}
                    className="rounded-md border border-input bg-background px-1.5 py-1 text-xs flex-1 min-w-[80px]"
                  />
                )}
                {!noValue && c.op === "between" && (
                  <>
                    <input
                      type={t === "integer" || t === "double" ? "number" : t === "date" ? "date" : "text"}
                      value={c.value}
                      onChange={(e) => update(idx, { value: e.target.value })}
                      placeholder="from"
                      className="rounded-md border border-input bg-background px-1.5 py-1 text-xs w-[80px]"
                    />
                    <span className="text-[10px] text-muted-foreground">and</span>
                    <input
                      type={t === "integer" || t === "double" ? "number" : t === "date" ? "date" : "text"}
                      value={c.value2 ?? ""}
                      onChange={(e) => update(idx, { value2: e.target.value })}
                      placeholder="to"
                      className="rounded-md border border-input bg-background px-1.5 py-1 text-xs w-[80px]"
                    />
                  </>
                )}
                <button
                  type="button"
                  onClick={() => removeCond(idx)}
                  disabled={conds.length === 1}
                  aria-label="Remove condition"
                  className="ml-auto text-muted-foreground hover:text-destructive disabled:opacity-30"
                >
                  ✕
                </button>
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>

      <div className="flex items-center gap-2 text-xs">
        <button
          type="button"
          onClick={addCond}
          className="rounded-md border border-dashed border-border px-2 py-1 text-muted-foreground hover:text-foreground hover:border-foreground/40"
        >
          ➕ Add condition
        </button>
        <span className="flex-1" />
        <button
          type="button"
          onClick={() => setMode("sql")}
          className="text-[11px] text-muted-foreground hover:text-foreground underline-offset-2 hover:underline"
          title="Switch to raw SQL editor"
        >
          {`</> SQL mode`}
        </button>
      </div>

      {generatedSql && (
        <p className="text-[10px] text-muted-foreground/70 font-mono leading-tight bg-muted/30 rounded px-2 py-1 break-all">
          {generatedSql}
        </p>
      )}
    </div>
  );
}
