"use client";

/**
 * Prompts for the API access token when the backend rejects a request with 401.
 *
 * Why this exists: the token used to be compiled into the JavaScript bundle via
 * `NEXT_PUBLIC_DIG_AUTH_TOKEN`, which meant it was served to anyone who could
 * load the page — in LAN mode, precisely the people it was meant to keep out.
 * The web tier has no login of its own, so it can't decide who deserves the
 * token; the person using the browser supplies it instead.
 *
 * Stored in `sessionStorage`, so it dies with the tab rather than lingering on
 * a shared machine.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { getApiToken, setApiToken } from "@/lib/api/client";

export function TokenGate() {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [hadToken, setHadToken] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const restoreFocusTo = useRef<Element | null>(null);

  useEffect(() => {
    const onAuthRequired = () => {
      setHadToken(Boolean(getApiToken()));
      restoreFocusTo.current = document.activeElement;
      setOpen(true);
    };
    window.addEventListener("dig:auth-required", onAuthRequired);
    return () => window.removeEventListener("dig:auth-required", onAuthRequired);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const close = useCallback(() => {
    setOpen(false);
    setValue("");
    // Put focus back where it was — the dialog appears unprompted, so leaving
    // focus on <body> would strand a keyboard user.
    (restoreFocusTo.current as HTMLElement | null)?.focus?.();
  }, []);

  const submit = useCallback(() => {
    const t = value.trim();
    if (!t) return;
    setApiToken(t);
    close();
    // Simplest correct way to re-run everything that failed: the queries that
    // 401'd are already in an error state across the app, and a reload also
    // re-establishes the WebSocket with the new token.
    window.location.reload();
  }, [value, close]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"
      role="presentation"
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="token-gate-title"
        aria-describedby="token-gate-desc"
        className="w-full max-w-md rounded-lg border border-border bg-card p-5 shadow-2xl"
        onKeyDown={(e) => {
          if (e.key === "Escape") close();
        }}
      >
        <h2 id="token-gate-title" className="text-base font-semibold mb-1">
          🔑 Access token required
        </h2>
        <p id="token-gate-desc" className="text-sm text-muted-foreground mb-3">
          {hadToken
            ? "The server rejected the token for this tab. Enter the current one to continue."
            : "This DIG server is protected. Paste its access token to continue — it is kept for this browser tab only."}
        </p>
        <label htmlFor="token-gate-input" className="sr-only">
          API access token
        </label>
        <input
          id="token-gate-input"
          ref={inputRef}
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
          placeholder="Paste token"
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus-visible:ring-3 focus-visible:ring-ring outline-none"
        />
        <p className="mt-2 text-[11px] text-muted-foreground">
          The operator can find it in the server&apos;s startup output, or in{" "}
          <code>~/.config/dig/auth-token</code>.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={close}
            className="rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={!value.trim()}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 focus-visible:ring-3 focus-visible:ring-ring outline-none"
          >
            Use token
          </button>
        </div>
      </div>
    </div>
  );
}
