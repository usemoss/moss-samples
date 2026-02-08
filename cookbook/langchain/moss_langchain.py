from typing import Any, List, Optional
import os
from pydantic import Field, PrivateAttr
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun, AsyncCallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.tools import Tool
from inferedge_moss import MossClient, QueryOptions
import asyncio

class MossRetriever(BaseRetriever):
    """Moss semantic search retriever."""
    
    project_id: str = Field(description="Moss project ID")
    project_key: str = Field(description="Moss project key")
    index_name: str = Field(description="Name of the Moss index to query")
    top_k: int = Field(default=5, description="Number of results to return")
    alpha: float = Field(default=0.5, description="Controls hybrid search")
    _client: Any = PrivateAttr()
    _index_loaded: bool = PrivateAttr(default=False)

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the retriever."""
        super().__init__(**kwargs)
        self._client = MossClient(self.project_id, self.project_key)

    async def _ensure_loaded(self) -> None:
        if not self._index_loaded:
            await self._client.load_index(self.index_name)
            self._index_loaded = True

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        """Synchronous retrieval. 
        Note: This will fail if called from a running event loop (like a Jupyter notebook).
        In such cases, use `ainvoke` instead.
        """
        try:
            return asyncio.run(self._aget_relevant_documents(query))
        except RuntimeError as e:
            if "asyncio.run() cannot be called from a running event loop" in str(e):
                raise RuntimeError(
                    "MossRetriever.invoke() cannot be called from a running event loop (e.g., in a Jupyter notebook). "
                    "Please use 'await MossRetriever.ainvoke()' instead."
                ) from e
            raise e

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: Optional[AsyncCallbackManagerForRetrieverRun] = None
    ) -> List[Document]:
        """Asynchronous retrieval from Moss."""
        await self._ensure_loaded()
        
        results = await self._client.query(
            self.index_name, 
            query, 
            QueryOptions(top_k=self.top_k, alpha=self.alpha)
        )
        
        docs = []
        for doc in results.docs:
            docs.append(
                Document(
                    page_content=doc.text,
                    metadata={"score": doc.score, "id": doc.id}
                )
            )
        return docs

def get_moss_tool(project_id: str, project_key: str, index_name: str, top_k: int = 5,alpha:float=0) -> Tool:
    """Create a LangChain Tool for Moss semantic search."""
    
    retriever = MossRetriever(
        project_id=project_id,
        project_key=project_key,
        index_name=index_name,
        top_k=top_k,
        alpha=alpha
    )

    async def asearch(query: str) -> str:
        docs = await retriever._aget_relevant_documents(query)
        if not docs:
            return "No relevant information found."
        
        return "\n\n".join([f"Result {i+1}:\n{doc.page_content}" for i, doc in enumerate(docs)])

    def search(query: str) -> str:
        # Note: Tool search function should be sync if called by non-async agents,
        # but LangChain handles choosing between func and coroutine.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
            
        if loop and loop.is_running():
            # This is tricky in notebooks. 
            # For simplicity in the cookbook, we'll assume asearch is used.
            return "Error: Use async for this tool in this environment."
        return asyncio.run(asearch(query))

    return Tool(
        name="moss_search",
        description="Search for information in the company's knowledge base using Moss semantic search. "
                    "Useful for answering questions about company policies, FAQs, and product details.",
        func=search,
        coroutine=asearch
    )