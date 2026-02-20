<!-- markdownlint-disable-next-line MD033 -->

# <img src="https://github.com/user-attachments/assets/c4e39933-40c4-462d-a9a3-135458c6705f" alt="Moss logo" width="48" style="vertical-align: middle; margin-right: 8px;" /> Moss Samples

[![License](https://img.shields.io/badge/License-BSD_2--Clause-orange.svg)](https://opensource.org/licenses/BSD-2-Clause)
[![Discord](https://img.shields.io/discord/1433962929526542346?logo=discord&logoColor=7289da&label=Discord)](https://discord.gg/eMXExuafBR)

Working examples for [Moss](https://moss.dev) — the real-time search runtime for AI agents.

Each sample is kept thin on purpose. Copy what you need straight into your own project, swap in your data, and go. Python, TypeScript, Next.js, and Pipecat voice agents are all covered.

**Questions? Join our [Discord](https://discord.gg/eMXExuafBR).**

---

## Setup

1. Sign up at [moss.dev](https://moss.dev/) and create an index from the dashboard.
2. Open **View secrets** and save the values to your `.env`:

```bash
MOSS_PROJECT_ID=your_project_id
MOSS_PROJECT_KEY=your_project_key
```

> ![Moss Portal walkthrough](https://github.com/user-attachments/assets/c3db9d2d-0df5-4cec-99fd-7d49d0a30844)

For full setup details and pricing, see the [docs](https://docs.moss.dev).

---

## Python

Install deps: `pip install -r python/requirements.txt`, then run any script with `python path/to/sample.py`.

- [`comprehensive_sample.py`](python/comprehensive_sample.py) — end-to-end flow: session creation, context building, streaming responses
- [`load_and_query_sample.py`](python/load_and_query_sample.py) — ingest domain knowledge, then query
- [`custom_embedding_sample.py`](python/custom_embedding_sample.py) — create an index with custom OpenAI embeddings and run queries

> ![Moss Python walkthrough](https://github.com/user-attachments/assets/d826023d-92d6-49ac-8e5e-81cf04d409c5)

## TypeScript

Install deps: `npm install` inside `javascript/`, then run with `npm run start -- path/to/sample.ts`.

- [`comprehensive_sample.ts`](javascript/comprehensive_sample.ts) — full workflow in TypeScript, ready for Node
- [`load_and_query_sample.ts`](javascript/load_and_query_sample.ts) — index FAQs and issue targeted queries
- [`custom_embedding_sample.ts`](javascript/custom_embedding_sample.ts) — provision an index, push OpenAI embeddings, query

## Next.js

A web-based semantic search interface using Next.js 15 and Server Actions. Shows how to call Moss securely from the server while serving a responsive UI.

```bash
cd next-js && npm install && npm run dev
```

Open `http://localhost:3000`. See the [`next-js/`](next-js/) directory for details.

## Pipecat Voice Agent

A voice bot that plugs Moss retrieval into [Pipecat's](https://github.com/pipecat-ai/pipecat) real-time pipeline — sub-10ms semantic search for a customer support agent.

- [`pipecat-moss/pipecat-quickstart/`](pipecat-moss/pipecat-quickstart/) — ingest FAQs with `create-index.py`, wire into Pipecat, deploy to Pipecat Cloud
- For deeper context, see the [Pipecat-Moss repo](https://github.com/usemoss/pipecat-moss)

---

## Learn more

- [Documentation](https://docs.moss.dev) — API reference, guides, architecture
- [Website](https://moss.dev) — product overview and pricing
- [Launch YC post](https://www.ycombinator.com/launches/Oiq-moss-real-time-semantic-search-for-conversational-ai)

## Contributing

If you spot gaps or want another language example, open an issue or PR. We track feedback closely.

See our [Contributing Guide](CONTRIBUTING.md) for details.

## License

[BSD 2-Clause License](LICENSE)