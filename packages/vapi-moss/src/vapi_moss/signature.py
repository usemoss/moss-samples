#
# Copyright (c) 2025-2026, InferEdge Inc.
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""VAPI webhook signature verification."""

from __future__ import annotations

import hashlib
import hmac

__all__ = ["verify_vapi_signature"]


def verify_vapi_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    """Verify a VAPI webhook signature against raw request bytes.

    VAPI signs webhooks with HMAC-SHA256 and sends the signature in the
    ``x-vapi-signature`` header as ``sha256=<hex-digest>``.

    This function MUST receive the raw request body bytes, not a re-serialized
    dict, because any differences in serialization will break the comparison.

    Args:
        raw_body: The raw HTTP request body bytes.
        signature_header: The ``x-vapi-signature`` header value.
        secret: The webhook secret configured when creating the knowledge base.

    Returns:
        True if the signature is valid.
    """
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()

    normalized = signature_header.strip()
    if "=" in normalized:
        algorithm, _, provided = normalized.partition("=")
        if algorithm.strip().lower() != "sha256":
            return False
    else:
        provided = normalized

    return hmac.compare_digest(expected, provided.strip().lower())
