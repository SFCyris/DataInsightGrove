"use client";

import { useEffect, useMemo, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  type ColDef,
  type GridReadyEvent,
  type IDatasource,
  type IGetRowsParams,
} from "ag-grid-community";
import { api, type ColumnInfo } from "@/lib/api/client";

ModuleRegistry.registerModules([AllCommunityModule]);

const TYPE_EMOJI: Record<string, string> = {
  integer: "🔢",
  double: "🔢",
  string: "🅰️",
  date: "📅",
  datetime: "📅",
  boolean: "☑️",
  nested: "🧱",
};

const lightTheme = themeQuartz.withParams({
  fontFamily: "var(--font-geist-sans), ui-sans-serif",
  headerFontSize: 12,
  fontSize: 13,
  borderRadius: 10,
  rowBorder: { style: "dashed", width: 1, color: "color-mix(in srgb, currentColor 8%, transparent)" },
  spacing: 6,
  headerBackgroundColor: "color-mix(in srgb, currentColor 5%, transparent)",
  oddRowBackgroundColor: "transparent",
  rowHoverColor: "color-mix(in srgb, currentColor 6%, transparent)",
});

interface Props {
  datasetId: string;
  columns: ColumnInfo[];
  totalRows: number | null | undefined;
}

export function DatasetGrid({ datasetId, columns, totalRows }: Props) {
  const [gridReady, setGridReady] = useState(false);

  const colDefs = useMemo<ColDef[]>(() => {
    return columns.map((c) => ({
      field: c.name,
      headerName: c.name,
      headerComponentParams: { type: c.type },
      minWidth: 110,
      flex: 1,
      sortable: false,
      filter: false,
      resizable: true,
      cellClass: c.type === "integer" || c.type === "double" ? "tabular-nums text-right" : "",
      headerClass: "text-xs font-medium",
      headerTooltip: `${TYPE_EMOJI[c.type] ?? "❔"} ${c.type}${c.polarsType ? ` · ${c.polarsType}` : ""}`,
    }));
  }, [columns]);

  const datasource = useMemo<IDatasource>(
    () => ({
      rowCount: totalRows ?? undefined,
      getRows: async (params: IGetRowsParams) => {
        try {
          const limit = params.endRow - params.startRow;
          const page = await api.getRows(datasetId, params.startRow, limit);
          const totalKnown = page.totalRows ?? totalRows ?? null;
          // If we know total rows, signal end-of-data via the totalCount param.
          const lastRow =
            totalKnown != null
              ? totalKnown
              : page.rows.length < limit
                ? params.startRow + page.rows.length
                : -1;
          params.successCallback(page.rows, lastRow ?? -1);
        } catch (e) {
          console.error("getRows failed", e);
          params.failCallback();
        }
      },
    }),
    [datasetId, totalRows],
  );

  return (
    // `relative` so the loading overlay positions against this box; without
    // it the absolute overlay anchored to the viewport and blocked unrelated
    // UI until the grid mounted.
    <div className="relative h-[640px] w-full">
      <AgGridReact
        theme={lightTheme}
        columnDefs={colDefs}
        rowModelType="infinite"
        cacheBlockSize={200}
        cacheOverflowSize={2}
        maxBlocksInCache={20}
        infiniteInitialRowCount={Math.min(totalRows ?? 1000, 1000)}
        datasource={datasource}
        rowHeight={32}
        headerHeight={36}
        suppressCellFocus={false}
        animateRows={true}
        onGridReady={(_e: GridReadyEvent) => setGridReady(true)}
      />
      {!gridReady && (
        <div className="absolute inset-0 grid place-items-center text-muted-foreground text-sm">
          ⏳ Loading grid…
        </div>
      )}
    </div>
  );
}
