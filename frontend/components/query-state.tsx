"use client";

/**
 * Renders the three states a data-fetching surface actually has — loading,
 * failed, empty — instead of collapsing failure into "no data".
 *
 * Several list routes were structured as `isLoading ? skeleton : items.length
 * === 0 ? empty : list`, which has no branch for an error. With the backend
 * down, `/runs` told the user "No runs match these filters" (offering to clear
 * filters that weren't the problem) and `/catalog` rendered nothing under a
 * "0 pipelines" heading. Both are actively misleading: they assert a fact
 * about the user's data when the truth is that DIG couldn't ask.
 *
 * `retry: 1` and `refetchOnWindowFocus: false` (lib/query.tsx) mean nothing
 * self-heals either, so the error branch must offer an explicit retry.
 */

import type { UseQueryResult } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { PositiveLoader } from "@/components/positive-loader";

interface Props<T> {
  query: UseQueryResult<T>;
  /** Shown when the request succeeded and there is genuinely nothing to list. */
  empty?: React.ReactNode;
  /** Treats a successful response as empty (e.g. `d.items.length === 0`). */
  isEmpty?: (data: T) => boolean;
  /** What to render on success with data. */
  children: (data: T) => React.ReactNode;
  /** Optional primary text for the loading state. */
  loadingLabel?: string;
  /** Custom loading UI — pass an existing table/card skeleton to keep a
   *  route's zero-layout-shift frame instead of the generic loader. */
  loading?: React.ReactNode;
}

export function QueryState<T>({
  query,
  empty,
  isEmpty,
  children,
  loadingLabel,
  loading,
}: Props<T>) {
  if (query.isLoading) {
    return <>{loading ?? <PositiveLoader primary={loadingLabel} />}</>;
  }

  if (query.isError) return <QueryError query={query} />;

  if (query.data === undefined) return null;
  if (isEmpty?.(query.data)) return <>{empty ?? null}</>;
  return <>{children(query.data)}</>;
}

/** The error branch on its own, for routes whose loading/empty states are
 *  already bespoke (a table-shaped skeleton, a themed empty card). Drop it
 *  into the existing ternary chain ahead of the empty check so a failure
 *  stops being reported as "nothing here". */
export function QueryError({ query }: { query: Pick<UseQueryResult<unknown>, "error" | "refetch" | "isFetching"> }) {
  const msg = query.error instanceof Error ? query.error.message : String(query.error ?? "");
  return (
    <div role="alert" className="h-full grid place-items-center text-center text-sm text-muted-foreground p-8">
      <div>
        <div className="text-5xl mb-3 select-none" aria-hidden="true">🌧</div>
        <p className="mb-1 font-medium text-foreground">Couldn&apos;t load this</p>
        <p className="max-w-md mx-auto mb-4">
          This is a connection or server problem — it doesn&apos;t mean your data is missing.
        </p>
        {msg && (
          <p className="max-w-md mx-auto mb-4 text-[11px] font-mono break-words opacity-70">{msg}</p>
        )}
        <Button onClick={() => void query.refetch()} disabled={query.isFetching}>
          {query.isFetching ? "Retrying…" : "↻ Try again"}
        </Button>
      </div>
    </div>
  );
}
