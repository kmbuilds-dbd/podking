from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from podking.deps import current_user, get_db
from podking.models import Summary, SummaryTag, User
from podking.schemas import EpisodeResponse, SearchResult, SummaryResponse, SummaryTagResponse

router = APIRouter(prefix="/api")

_RRF_K = 60


@router.get("/search", response_model=list[SearchResult])
async def search(
    q: str = Query(min_length=1),
    tag: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> list[SearchResult]:
    """Hybrid search: full-text + vector cosine merged via Reciprocal Rank Fusion."""

    # Build the tag filter subquery if needed
    tag_filter = ""
    if tag:
        tag_filter = """
            AND s.id IN (
                SELECT st.summary_id FROM summary_tags st
                JOIN tags t ON t.id = st.tag_id
                WHERE t.user_id = :user_id AND t.name = :tag_name
            )
        """

    tsq = "websearch_to_tsquery('english', :q)"
    # Full-text ranking; embedding hybrid is additive once Voyage query embedding is wired in.
    fts_sql = text(f"""
        SELECT s.id,
               ts_rank_cd(s.tsv, {tsq}) AS rank,
               row_number() OVER (ORDER BY ts_rank_cd(s.tsv, {tsq}) DESC) AS rn
        FROM summaries s
        WHERE s.user_id = :user_id
          AND s.tsv @@ {tsq}
          {tag_filter}
        ORDER BY rank DESC
        LIMIT 50
    """)
    fts_params: dict[str, object] = {"user_id": user.id, "q": q}
    if tag:
        fts_params["tag_name"] = tag

    fts_result = await db.execute(fts_sql, fts_params)
    fts_rows = fts_result.fetchall()

    if not fts_rows:
        return []

    # RRF merge (FTS only for now; extend with vector scores when embedding query is added)
    rrf_scores: dict[object, float] = {}
    matched_fields_map: dict[object, list[str]] = {}
    for row in fts_rows:
        sid = row.id
        rrf_scores[sid] = rrf_scores.get(sid, 0.0) + 1.0 / (_RRF_K + row.rn)
        matched_fields_map[sid] = ["fulltext"]

    ranked_ids = sorted(rrf_scores.keys(), key=lambda sid: rrf_scores[sid], reverse=True)[:50]

    # Fetch full summary objects
    summaries_result = await db.execute(
        select(Summary)
        .where(Summary.id.in_(ranked_ids), Summary.user_id == user.id)
        .options(
            selectinload(Summary.episode),
            selectinload(Summary.summary_tags).selectinload(SummaryTag.tag),
        )
    )
    summaries_by_id: dict[object, Summary] = {s.id: s for s in summaries_result.scalars()}

    results: list[SearchResult] = []
    for sid in ranked_ids:
        summary = summaries_by_id.get(sid)
        if summary is None:
            continue
        tags = [
            SummaryTagResponse(name=st.tag.name, source=st.source)
            for st in summary.summary_tags
        ]
        summary_resp = SummaryResponse(
            id=summary.id,
            episode=EpisodeResponse.model_validate(summary.episode),
            system_prompt=summary.system_prompt,
            model=summary.model,
            content=summary.content,
            tags=tags,
            created_at=summary.created_at,
        )
        results.append(
            SearchResult(
                summary_id=summary.id,
                score=rrf_scores[sid],
                matched_fields=matched_fields_map[sid],
                episode=EpisodeResponse.model_validate(summary.episode),
                summary=summary_resp,
            )
        )

    return results
