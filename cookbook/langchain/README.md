# Moss LangChain Cookbook

This cookbook demonstrates how to integrate [Moss](https://moss.dev) with [LangChain](https://www.langchain.com/).

## Overview

Moss is a semantic search platform that allows you to build and query high-performance vector indices without managing infrastructure. This integration provides:

1.  **MossRetriever**: A LangChain-compatible retriever for semantic search.
2.  **MossSearchTool**: A tool for LangChain agents to search your knowledge base.

## Installation

Ensure you have the required packages installed:

```bash
pip install inferedge-moss langchain langchain-openai python-dotenv
```

## Setup

Create a `.env` file with your Moss credentials:

```env
MOSS_PROJECT_ID=your_project_id
MOSS_PROJECT_KEY=your_project_key
MOSS_INDEX_NAME=your_index_name
OPENAI_API_KEY=your_openai_api_key
```

## Usage

### Using the Retriever

The `MossRetriever` can be used in any LangChain chain.

```python
from moss_langchain import MossRetriever

retriever = MossRetriever(
    project_id="your_id",
    project_key="your_key",
    index_name="your_index",
    top_k=3,
    alpha=0
)

docs = retriever.invoke("What is the refund policy?")
```

### Using the Agent Tool

You can also use Moss as a tool for an agent.

```python
from moss_langchain import get_moss_tool

tool = get_moss_tool(
    project_id="your_id",
    project_key="your_key",
    index_name="your_index"
)

# Add to agent tools
tools = [tool]
```

## Examples

Check out the [moss_langchain.ipynb](moss_langchain.ipynb) notebook for complete examples including:

- Direct index querying
- Retrieval-Augmented Generation (RAG)
- ReAct Agent with Moss search
