"""Voyage AI embedding."""
from __future__ import annotations

import voyageai

MODEL = "voyage-3"


class VoyageError(RuntimeError):
    pass


async def embed(text: str, api_key: str) -> list[float]:
    """Return embedding vector of length 1024."""
    client = voyageai.AsyncClient(api_key=api_key)  # type: ignore[attr-defined]
    for attempt in range(3):
        try:
            result = await client.embed([text], model=MODEL, input_type="document")
            return list(result.embeddings[0])
        except Exception as exc:
            if attempt == 2:
                raise VoyageError(f"Voyage embedding failed: {exc}") from exc
            import asyncio
            await asyncio.sleep(2 ** attempt * 2)
    raise VoyageError("Voyage embedding failed after retries")
