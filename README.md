<!-- markdownlint-disable-next-line MD033 -->
# <img src="https://github.com/user-attachments/assets/c4e39933-40c4-462d-a9a3-135458c6705f" alt="Moss logo" width="48" style="vertical-align: middle; margin-right: 8px;" /> Moss Samples

[![CI](https://github.com/usemoss/moss-samples/actions/workflows/ci.yml/badge.svg)](https://github.com/usemoss/moss-samples/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Discord](https://img.shields.io/discord/1234567890?color=7289da&label=discord&logo=discord&logoColor=white)](https://discord.gg/eMXExuafBR)

Moss is a high-performance runtime for real-time semantic search. It delivers sub-10 ms lookups, instant index updates, and zero infra overhead. Moss runs where your agent lives - cloud, in-browser, or on-device - so search feels native and users never wait. You connect your data once; Moss handles indexing, packaging, distribution and updates.

This repo bundles thin, working examples that show how to talk to Moss from Python and JavaScript. Each sample keeps the scaffolding light so you can copy the essentials straight into your own projects.

**Join our [discord server](https://discord.gg/eMXExuafBR) to get onboarded!**

## Using Moss Portal

- Visit [usemoss.dev](https://usemoss.dev/) - click on signup/login on the top right
  - confirm your email, and sign in.
- Inside the default project you will see two plans:
  - Free Tier ($0) offers 1 project, 3 indexes, and 1,000 items per index with community support;
  - Developer Workspace ($2000/month + usage) adds unlimited projects/indexes plus 100 GB storage, 100 GB ingestion, 1 TB egress, and priority support.
- Enter valid card details to start the free trial, then select **Create Index** to provision a new index.
- From the dashboard, open **View secrets** and save the values as `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY` in your `.env` for the samples.

> ![Moss Portal walkthrough](https://github.com/user-attachments/assets/c3db9d2d-0df5-4cec-99fd-7d49d0a30844)

## Building with Moss

- Samples show how to authenticate, batch context, and stream replies without extra boilerplate.
- Adapt the scripts by swapping the FAQ JSON files with your data, or plugging Moss calls into an existing app.
 
## Python SDK Quick Tour

- [`python/comprehensive_sample.py`](python/comprehensive_sample.py): end-to-end flow with session creation, context building, and streaming responses.
- [`python/load_and_query_sample.py`](python/load_and_query_sample.py): how to ingest domain knowledge before querying Moss.
- Install deps with `pip install -r python/requirements.txt`, then run any script via `python path/to/sample.py`.

> ![Moss Python walkthrough](https://github.com/user-attachments/assets/d826023d-92d6-49ac-8e5e-81cf04d409c5)

## JavaScript SDK Quick Tour

- [`javascript/comprehensive_sample.ts`](javascript/comprehensive_sample.ts): TypeScript version of the full workflow, ready for Node.
- [`javascript/load_and_query_sample.ts`](javascript/load_and_query_sample.ts): demonstrates indexing FAQs and issuing targeted prompts.
- Install deps with `npm install` inside `javascript/`, then execute via `npm run start -- path/to/sample.ts`.

## Pipecat Voice Agent Quickstart

- [`pipecat-moss/pipecat-quickstart/`](pipecat-moss/pipecat-quickstart/):  Voice bot that plugs Moss retrieval into Pipecat’s real-time pipeline.
- Shows how to ingest FAQs with `create-index.py`, wire `pipecat-moss` package into Pipecat, and deploy to Pipecat Cloud.
- Use it to bootstrap a sub-10 ms semantic search customer support agent. For deeper context, see the project README and the [Pipecat-Moss repo](https://github.com/usemoss/pipecat-moss).

## Learn More

- API reference: [MOSS docs](https://docs.usemoss.dev/)
- Our [Launch YC Post!](https://www.ycombinator.com/launches/Oiq-moss-real-time-semantic-search-for-conversational-ai)

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for more information.

If you spot gaps or want another language example, open an issue or PR. We track feedback closely.

## Security

If you discover a security vulnerability, please send an e-mail to security@usemoss.dev.

## License

This project is licensed under the [MIT License](LICENSE).
