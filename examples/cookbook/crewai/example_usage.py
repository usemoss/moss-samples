import asyncio
import json
import os

from crewai import LLM, Agent, Crew, Task
from dotenv import load_dotenv
from moss import DocumentInfo, MossClient
from moss_crewai import MossSearchTool

load_dotenv()

client = MossClient(os.getenv("MOSS_PROJECT_ID"), os.getenv("MOSS_PROJECT_KEY"))

llm = LLM(
    model="gemini/gemini-2.5-flash",
    api_key=os.getenv("GEMINI_API_KEY"),
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

INDEXES = {
    "travel-destinations": {
        "file": "destinations_moss.json",
        "role": "Destinations Specialist",
        "goal": "Find destination guides, budget tips, and local travel advice",
        "backstory": "You are a travel destination expert. Always use the moss_search tool and return all results.",
    },
    "travel-stays": {
        "file": "stays_moss.json",
        "role": "Hotels & Stays Specialist",
        "goal": "Find accommodation options with pricing and amenities",
        "backstory": "You are an accommodation expert. Always use the moss_search tool and return all results.",
    },
    "travel-activities": {
        "file": "activities_moss.json",
        "role": "Activities & Tours Specialist",
        "goal": "Find tours, activities, and experiences with costs",
        "backstory": "You are an activities expert. Always use the moss_search tool and return all results.",
    },
}


async def setup_indexes():
    """Create travel indexes from Moss-formatted data."""
    for index_name, config in INDEXES.items():
        with open(os.path.join(DATA_DIR, config["file"])) as f:
            raw = json.load(f)

        docs = [
            DocumentInfo(id=item["id"], text=item["text"], metadata=item.get("metadata", {}))
            for item in raw
        ]

        print(f"Setting up '{index_name}' ({len(docs)} docs)...")
        try:
            await client.create_index(index_name, docs)
        except RuntimeError as e:
            if "already exists" not in str(e):
                raise
            print("  Already exists, skipping.")
        await client.load_index(index_name)
        print("  Loaded.")
    print()


def build_agents():
    """Create 3 specialist agents and a travel planner."""
    specialists = []
    for index_name, config in INDEXES.items():
        search = MossSearchTool(client=client, index_name=index_name, top_k=5)
        specialists.append(Agent(
            role=config["role"],
            goal=config["goal"],
            backstory=config["backstory"],
            tools=[search],
            llm=llm,
            verbose=False,
        ))

    writer = Agent(
        role="Travel Planner",
        goal="Create helpful travel plans from specialist findings",
        backstory=(
            "You are an experienced travel planner. Use specialist findings to craft "
            "a clear, actionable travel plan. Never make up information. "
            "Ignore results not relevant to the question."
        ),
        llm=llm,
        verbose=False,
    )
    return specialists, writer


def chat():
    """Interactive travel planner chat."""
    specialists, writer = build_agents()

    print("=== Moss + CrewAI Travel Planner ===")
    print("Plan your next trip! Type 'quit' to exit.\n")

    while True:
        question = input("You: ").strip()
        if not question or question.lower() in ("quit", "exit", "q"):
            if question:
                print("Goodbye!")
            break

        search_tasks = [
            Task(
                description=f"Use moss_search to find: '{question}'. Return ALL results as-is.",
                expected_output="Raw search results from the knowledge base.",
                agent=agent,
            )
            for agent in specialists
        ]

        write_task = Task(
            description=(
                f"A traveler asks: '{question}'\n\n"
                "Create a helpful travel plan using the specialist findings. "
                "Include specific recommendations with prices where available."
            ),
            expected_output="A friendly, actionable travel plan.",
            agent=writer,
            context=search_tasks,
        )

        crew = Crew(
            agents=specialists + [writer],
            tasks=search_tasks + [write_task],
            verbose=False,
        )
        result = crew.kickoff()
        print(f"\nAgent: {result}\n")


if __name__ == "__main__":
    asyncio.run(setup_indexes())
    chat()
