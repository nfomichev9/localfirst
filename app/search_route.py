"""Same-origin search endpoint for the shared browser chat transport."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .web_search import MAX_QUERY_CHARS, WebSearchError, search_web

router = APIRouter()


class SearchQuery(BaseModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)


@router.post('/api/browser-search')
async def browser_search(body: SearchQuery, request: Request):
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Use Search from the LocalFirst site.')
    try:
        return await search_web(body.query)
    except WebSearchError as exc:
        raise HTTPException(502, str(exc)) from exc
