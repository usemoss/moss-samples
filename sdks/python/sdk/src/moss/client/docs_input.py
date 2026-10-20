"""The document inputs `MossClient` and `SessionIndex` accept."""

from __future__ import annotations

import os
from typing import Any, Callable, Iterable, List, Mapping, Optional, Union

from moss_core import Chunking, DocumentInfo

DocsInput = Union[
    Iterable[DocumentInfo],
    Iterable[Mapping[str, Any]],
    Iterable["os.PathLike[str]"],
    str,
    bytes,
    "os.PathLike[str]",
]
Chunker = Callable[[str], List[str]]


def reject_chunking_for_custom(
    chunker: Optional[Chunker], chunking: Optional[Chunking], model_id: Optional[str]
) -> None:
    """Raise when a chunker or `chunking` would run for `model_id="custom"`, whose chunks would have no embeddings."""
    if (chunker is not None or chunking is not None) and model_id == "custom":
        raise ValueError(
            "chunker and chunking cannot be used with model_id='custom': chunks have no embeddings"
        )
