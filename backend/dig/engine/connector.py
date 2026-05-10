from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import polars as pl


class Connector(ABC):
    """Base class for data source / sink plugins.

    Subclasses live under `backend/connectors/<id>/connector.py` and are
    discovered by ConnectorRegistry. Each connector folder also contains a
    `manifest.json` validated against `shared/schemas/connector-manifest.schema.json`.
    """

    manifest: dict[str, Any]

    def __init__(self, manifest: dict[str, Any]) -> None:
        self.manifest = manifest

    @property
    def id(self) -> str:
        return self.manifest["id"]

    @property
    def version(self) -> str:
        return self.manifest["version"]

    @property
    def label(self) -> str:
        return self.manifest["label"]

    @property
    def kind(self) -> str:
        return self.manifest["kind"]  # source | sink | both

    @abstractmethod
    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        """Read data from `uri` lazily. Raises NotImplementedError on sink-only connectors."""
        raise NotImplementedError

    def write(self, frame: pl.DataFrame, uri: str, options: dict[str, Any]) -> None:
        """Materialize `frame` to `uri`. Raises NotImplementedError on source-only connectors."""
        raise NotImplementedError
