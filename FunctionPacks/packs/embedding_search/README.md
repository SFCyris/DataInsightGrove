# 🧭 Embedding search

k-NN + clustering on top of embedding columns produced by `embed_text`.

## Steps

| Step | Purpose |
| --- | --- |
| `nearest_neighbors`  | For each row, find the k closest rows by embedding distance |
| `semantic_cluster`   | Cluster the rows by their embeddings (Agglomerative) |

## Requirements

```bash
pip install "scikit-learn>=1.3"
```

## Changelog

### 0.1.0 — 2026-05-05

- Initial release.
