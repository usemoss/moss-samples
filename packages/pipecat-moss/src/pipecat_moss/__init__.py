#
# Copyright (c) 2026, Moss Team
#
# SPDX-License-Identifier: BSD-2-Clause
#

"""Moss vector database integration for Pipecat."""

from __future__ import annotations

from moss import (
    DocumentInfo,
    GetDocumentsOptions,
    IndexInfo,
    MossClient,
    SearchResult,
)

from .moss_retrieval_service import MossRetrievalService

__all__ = [
    "DocumentInfo",
    "GetDocumentsOptions",
    "IndexInfo",
    "MossClient",
    "MossRetrievalService",
    "SearchResult",
]
