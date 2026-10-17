import json
import os

from dotenv import load_dotenv
from haystack import Document, Pipeline
from haystack.components.builders import PromptBuilder
from haystack.components.generators import OpenAIGenerator
from haystack.components.joiners import DocumentJoiner
from haystack.utils import Secret
from moss_haystack import MossDocumentStore, MossRetriever

load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

PROMPT_TEMPLATE = """
You are a helpful life assistant. You have access to two knowledge bases:
- Personal habits: the user's daily routines, fitness schedule, diet, and preferences
- General knowledge: tips, research, and advice on health, fitness, and productivity

Answer the question using the context below. If it's a personal question, be specific
about the user's habits. If it's general, give helpful advice. If both are relevant,
combine personal context with general advice.

Context:
{% for doc in documents %}
- {{ doc.content }}
{% endfor %}

Question: {{ query }}

Answer:
"""


PERSONAL_KEYWORDS = [
    " my ", " i ", " me ", " mine ", "do i ", "am i ","my routine", "my schedule", "my diet", "my workout",
]

GENERAL_KEYWORDS = [
    "how to", "tips for", "benefits of", "best way",
    "recommend", "ideal", "research", "studies show", "how much",
    "how long should", "how often should",
]


def route_query(query: str) -> str:
    """Route query based on keywords: personal, general, or combined."""
    q = f" {query.lower()} "
    is_personal = any(kw in q for kw in PERSONAL_KEYWORDS)
    is_general = any(kw in q for kw in GENERAL_KEYWORDS)

    if is_personal and is_general:
        return "combined"
    if is_personal:
        return "personal"
    if is_general:
        return "general"
    return "combined"


def load_index(name, data_file):
    """Load data into a Moss index."""
    with open(os.path.join(DATA_DIR, data_file)) as f:
        raw = json.load(f)

    docs = [
        Document(id=item["id"], content=item["text"], meta=item.get("metadata", {}))
        for item in raw
    ]

    store = MossDocumentStore(index_name=name)
    try:
        store.count_documents()
        print(f"  '{name}' already exists.")
    except RuntimeError:
        print(f"  Creating '{name}' ({len(docs)} docs)...")
        store.write_documents(docs)

    return store


def make_rag_pipe(retriever):
    """Build a RAG pipeline: retriever → prompt → LLM."""
    pipe = Pipeline()
    pipe.add_component("retriever", retriever)
    pipe.add_component("prompt", PromptBuilder(
        template=PROMPT_TEMPLATE, required_variables=["documents", "query"]
    ))
    pipe.add_component("llm", OpenAIGenerator(
        api_key=Secret.from_token(os.getenv("GEMINI_API_KEY")),
        model="gemini-3-flash-preview",
        api_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    ))
    pipe.connect("retriever.documents", "prompt.documents")
    pipe.connect("prompt", "llm")
    return pipe


def build_pipelines(personal_store, general_store):
    """Build three RAG pipelines — personal, general, and combined."""
    # Combined: both retrievers → joiner → prompt → LLM
    combined = Pipeline()
    combined.add_component(
        "personal_retriever", MossRetriever(document_store=personal_store, top_k=3)
    )
    combined.add_component(
        "general_retriever", MossRetriever(document_store=general_store, top_k=3)
    )
    combined.add_component("joiner", DocumentJoiner())
    combined.add_component("prompt", PromptBuilder(
        template=PROMPT_TEMPLATE, required_variables=["documents", "query"]
    ))
    combined.add_component("llm", OpenAIGenerator(
        api_key=Secret.from_token(os.getenv("GEMINI_API_KEY")),
        model="gemini-3-flash-preview",
        api_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    ))
    combined.connect("personal_retriever.documents", "joiner.documents")
    combined.connect("general_retriever.documents", "joiner.documents")
    combined.connect("joiner.documents", "prompt.documents")
    combined.connect("prompt", "llm")

    return {
        "personal": make_rag_pipe(MossRetriever(document_store=personal_store, top_k=3)),
        "general": make_rag_pipe(MossRetriever(document_store=general_store, top_k=3)),
        "combined": combined,
    }


def main():
    print("Setting up indexes...")
    personal_store = load_index("life-personal", "personal_habits.json")
    general_store = load_index("life-general", "general_knowledge.json")
    print()

    pipes = build_pipelines(personal_store, general_store)

    print("=== Life Assistant (Haystack + Moss) ===")
    print("Ask about your habits or get general advice.")
    print("Type 'quit' to exit.\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        route = route_query(question)
        pipe = pipes[route]
        print(f"  [Routed to: {route}]")

        try:
            if route == "combined":
                result = pipe.run({
                    "personal_retriever": {"query": question},
                    "general_retriever": {"query": question},
                    "prompt": {"query": question},
                })
            else:
                result = pipe.run({
                    "retriever": {"query": question},
                    "prompt": {"query": question},
                })
            answer = result["llm"]["replies"][0]
            print(f"\nAssistant: {answer}\n")
        except Exception as e:
            print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
