"""
Simplified Streaming API for Moss-powered FAQ Support
======================================================
Minimal FastAPI streaming endpoint using Moss semantic search + OpenAI.
"""

import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from inferedge_moss import MossClient
from openai import AsyncOpenAI
from pydantic import BaseModel

load_dotenv(".env")

# Initialize
app = FastAPI(title="Moss Streaming FAQ API")
moss_client = MossClient(
    os.environ["MOSS_PROJECT_ID"],
    os.environ["MOSS_PROJECT_KEY"]
)
moss_index_name = os.environ["MOSS_INDEX_NAME"]
openai_client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])


class Query(BaseModel):
    question: str
    max_results: int = 6


async def stream_response(question: str, max_results: int) -> AsyncGenerator[str, None]:
    """Search Moss FAQs and stream LLM response."""
    
    # 1. Search Moss
    results = await moss_client.query(moss_index_name, question, max_results)
    docs = list(getattr(results, "docs", []) or [])
    faq_context = "\n\n".join((doc.text or "").strip() for doc in docs)
    
    # 2. Build prompt
    system_prompt = f"""You are a customer support agent. Use the FAQ context below to answer questions.

FAQ Context:
{faq_context}"""
    
    # 3. Stream OpenAI response
    stream = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question}
        ],
        stream=True,
        temperature=0.7
    )
    
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


@app.post("/query")
async def query(q: Query):
    """Stream FAQ-powered response."""
    return StreamingResponse(
        stream_response(q.question, q.max_results),
        media_type="text/plain"
    )


@app.on_event("startup")
async def startup():
    """Preload Moss index."""
    await moss_client.load_index(moss_index_name)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("streaming_api:app", host="0.0.0.0", port=8000, reload=True)

