"""Tests for per-user analysis prompt styles."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_prompt_styles_includes_general(seeded_client: AsyncClient) -> None:
    response = await seeded_client.get("/api/prompt-styles")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["label"] == "general"
    assert data[0]["prompt_text"] == "Summarize this."


@pytest.mark.asyncio
async def test_prompt_style_crud_and_general_cannot_be_deleted(
    seeded_client: AsyncClient,
) -> None:
    created = await seeded_client.post(
        "/api/prompt-styles",
        json={"label": "technical", "prompt_text": "Focus on technical details."},
    )
    assert created.status_code == 201
    style = created.json()

    duplicate = await seeded_client.post(
        "/api/prompt-styles",
        json={"label": "technical", "prompt_text": "Another prompt."},
    )
    assert duplicate.status_code == 409

    updated = await seeded_client.patch(
        f"/api/prompt-styles/{style['id']}",
        json={"label": "technical deep-dive", "prompt_text": "Go deep."},
    )
    assert updated.status_code == 200
    assert updated.json()["label"] == "technical deep-dive"
    assert updated.json()["prompt_text"] == "Go deep."

    cannot_rename_general = await seeded_client.patch(
        f"/api/prompt-styles/{(await seeded_client.get('/api/prompt-styles')).json()[0]['id']}",
        json={"label": "renamed general"},
    )
    assert cannot_rename_general.status_code == 409

    general = (await seeded_client.get("/api/prompt-styles")).json()[0]
    cannot_delete = await seeded_client.delete(f"/api/prompt-styles/{general['id']}")
    assert cannot_delete.status_code == 409

    deleted = await seeded_client.delete(f"/api/prompt-styles/{style['id']}")
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_deleting_style_reassigns_subscriptions_to_general(
    seeded_client: AsyncClient,
) -> None:
    subscription = await seeded_client.post(
        "/api/subscriptions",
        json={"url": "https://feeds.example.com/style-fallback.xml"},
    )
    style = await seeded_client.post(
        "/api/prompt-styles",
        json={"label": "temporary", "prompt_text": "Temporary guidance."},
    )
    await seeded_client.patch(
        f"/api/subscriptions/{subscription.json()['id']}",
        json={"prompt_style_id": style.json()["id"]},
    )

    deleted = await seeded_client.delete(f"/api/prompt-styles/{style.json()['id']}")
    assert deleted.status_code == 204

    subscriptions = await seeded_client.get("/api/subscriptions")
    assert subscriptions.status_code == 200
    assert subscriptions.json()[0]["prompt_style"]["label"] == "general"
