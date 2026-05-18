#!/usr/bin/env python3
"""Generate a synthetic ecommerce-events dataset for the v1 50 GB
benchmark. Writes a single Parquet file using DuckDB's range() and
streaming COPY — much faster than Python-side row construction for
~10^8+ rows.

Target shape per row (~110 bytes uncompressed):
  event_ts        BIGINT     (ms epoch)
  user_id         BIGINT
  country_code    VARCHAR(2) (one of 12 ISO codes — used by the choropleth)
  category        VARCHAR    (one of 8 product categories)
  product_id      BIGINT
  amount          DOUBLE
  quantity        INT
  session_id      VARCHAR    (sess_<random>)

500M rows × ~110 bytes = ~55 GB uncompressed. ZSTD-compressed Parquet
typically lands in the 5–15 GB range depending on cardinality of the
string columns.
"""
import argparse
import os
import sys
import time
from pathlib import Path

import duckdb


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rows", type=int, default=500_000_000,
                   help="Total row count (default 500M).")
    p.add_argument("--out", default="data/inputs/ecommerce_benchmark.parquet",
                   help="Output Parquet path (relative to repo root).")
    p.add_argument("--threads", type=int, default=0,
                   help="DuckDB threads (0 = auto).")
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    out_path = (repo_root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[gen] target: {args.rows:,} rows → {out_path}", flush=True)
    print(f"[gen] est. uncompressed: ~{args.rows * 110 / 1024**3:.1f} GB", flush=True)

    con = duckdb.connect()
    if args.threads > 0:
        con.execute(f"PRAGMA threads={args.threads}")
    # Don't blow out memory: cap the work-mem so the COPY streams.
    con.execute("PRAGMA memory_limit='32GB'")
    con.execute("PRAGMA temp_directory='" + str(out_path.parent) + "'")

    t0 = time.time()
    # Generate in one shot via range() — DuckDB streams to Parquet without
    # materialising the full table in RAM.
    sql = f"""
    COPY (
      SELECT
        1700000000000 + (s * 7)::BIGINT                              AS event_ts,
        ((random() * 10_000_000)::BIGINT)                            AS user_id,
        ['US','GB','DE','FR','CA','JP','AU','IN','BR','MX','IT','ES'][1 + ((s::INTEGER) % 12)] AS country_code,
        ['electronics','apparel','books','home','beauty','sports','toys','grocery'][1 + ((s::INTEGER) % 8)] AS category,
        ((random() * 1_000_000)::BIGINT)                             AS product_id,
        round((random() * 500.0)::DOUBLE, 2)                          AS amount,
        (1 + (random() * 5)::INTEGER)                                AS quantity,
        'sess_' || ((random() * 10_000_000_000)::BIGINT)::VARCHAR    AS session_id
      FROM range({args.rows}) tbl(s)
    ) TO '{out_path}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 1_000_000);
    """
    con.execute(sql)
    dt = time.time() - t0

    size = out_path.stat().st_size
    print(f"[gen] done in {dt:.1f}s · {size/1024**3:.2f} GB on disk "
          f"({size*100/(args.rows*110):.1f}% of uncompressed est.)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
