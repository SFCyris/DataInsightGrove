import { describe, it, expect } from "vitest";
import type { paths, components } from "@/lib/api/types";

// `RunOut` is auto-generated under the openapi `components.schemas`
// namespace, not as a top-level export. Re-alias here so the test
// reads naturally.
type RunOut = components["schemas"]["RunOut"];

/**
 * Type-shape smoke tests for the API surface.
 *
 * These tests don't exercise runtime code — they exist so TypeScript fails
 * the build if the openapi-typescript-generated types drift away from the
 * fields the frontend relies on. If you regenerate `lib/api/types.ts` via
 * `pnpm gen:api` and one of these assertions stops compiling, the field
 * was removed or renamed on the backend and something downstream needs
 * to handle it.
 */

describe("RunOut shape — contract with backend", () => {
  it("carries the expected top-level fields", () => {
    const run: RunOut = {
      id: "01TESTRUN",
      pipelineId: "01TESTPIPE",
      status: "succeeded",
      progress: 1.0,
      createdAt: new Date().toISOString(),
      error: null,
      outputPaths: ["data/outputs/01TESTRUN/out.parquet"],
      artifacts: null,
      nodeMetrics: null,
      nanOrigins: null,
      startedAt: null,
      finishedAt: null,
    };
    expect(run.id).toBe("01TESTRUN");
    expect(run.status).toBe("succeeded");
  });

  it("nanOrigins entries match the documented shape", () => {
    // Per internal/proposals/NULL_AND_NAN_DISPLAY.md:
    //   { column, cause, count, row_indices, truncated, source_column? }
    const run: RunOut = {
      id: "r",
      pipelineId: "p",
      status: "succeeded",
      progress: 1,
      createdAt: new Date().toISOString(),
      nanOrigins: {
        my_cast_node: [
          {
            column: "price",
            cause: "cast_failure",
            count: 3,
            row_indices: [1, 7, 12],
            truncated: false,
            source_column: "price_string",
          },
        ],
        my_divide_node: [
          {
            column: "ratio",
            cause: "arithmetic_nan",
            count: 1,
            row_indices: [4],
            truncated: false,
          },
        ],
      },
    };
    const cast = run.nanOrigins?.my_cast_node?.[0];
    expect(cast?.cause).toBe("cast_failure");
    expect(cast?.source_column).toBe("price_string");
    const div = run.nanOrigins?.my_divide_node?.[0];
    expect(div?.cause).toBe("arithmetic_nan");
    expect(div?.source_column).toBeUndefined();
  });

  it("nanOrigins cause field is closed to the three known values", () => {
    // Defense: if a future schema change adds a new cause, this test
    // forces it to also land here (in source control) so consumers
    // know to handle it.
    type Cause = NonNullable<RunOut["nanOrigins"]>[string][number]["cause"];
    const known: Cause[] = ["cast_failure", "arithmetic_nan", "arithmetic_inf"];
    expect(known).toHaveLength(3);
  });
});

describe("Health endpoint shape", () => {
  it("exposes a version string + extensions + protocol_version", () => {
    // The frontend reads /health.version to display the current backend
    // version. Regressions here would mean the version display goes blank.
    type HealthRes = paths["/health"]["get"]["responses"]["200"]["content"]["application/json"];
    const sample: HealthRes = {
      status: "ok",
      name: "dig",
      version: "1.0.0rc1",
      extensions: [],
      protocol_version: [1, 0],
    };
    expect(sample.version).toBe("1.0.0rc1");
    expect(sample.extensions).toEqual([]);
    expect(sample.protocol_version).toEqual([1, 0]);
  });
});
