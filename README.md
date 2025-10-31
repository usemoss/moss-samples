<!-- markdownlint-disable-next-line MD033 -->
# <img src="https://github.com/user-attachments/assets/c4e39933-40c4-462d-a9a3-135458c6705f" alt="Moss logo" width="48" style="vertical-align: middle; margin-right: 8px;" /> Moss Samples

This repo bundles thin, working examples that show how to talk to Moss from Python and JavaScript. Each sample keeps the scaffolding light so you can copy the essentials straight into your own projects.

## Using Moss Portal

![Moss Portal walkthrough](https://github.com/user-attachments/assets/c3db9d2d-0df5-4cec-99fd-7d49d0a30844)

- Visit [portal.usemoss.dev/auth/login](https://portal.usemoss.dev/auth/login) to create an account, confirm your email, and sign in.
- Inside the default project you will see two plans: Free Tier ($0) offers 1 project, 3 indexes, and 1,000 items per index with community support; Developer Workspace ($2000/month + usage) adds unlimited projects/indexes plus 100 GB storage, 100 GB ingestion, 1 TB egress, and priority support.
- Enter valid card details to start the free trial, then select **Create Index** to provision a new index.
- From the dashboard, open **View secrets** and save the values as `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY` in your `.env` for the samples.

## Building with Moss

- Moss is an AI assistant platform; you send conversation state plus optional knowledge, Moss returns grounded answers.
- Samples show how to authenticate, batch context, and stream replies without extra boilerplate.
- Adapt the scripts by swapping the FAQ JSON files with your data, or plugging Moss calls into an existing app.
  
## Python SDK Quick Tour

![Moss Python walkthrough](https://github.com/user-attachments/assets/d826023d-92d6-49ac-8e5e-81cf04d409c5)

- [`python/comprehensive_sample.py`](python/comprehensive_sample.py): end-to-end flow with session creation, context building, and streaming responses.
- [`python/load_and_query_sample.py`](python/load_and_query_sample.py): how to ingest domain knowledge before querying Moss.
- Install deps with `pip install -r python/requirements.txt`, then run any script via `python path/to/sample.py`.

## JavaScript SDK Quick Tour

- [`javascript/comprehensive_sample.ts`](javascript/comprehensive_sample.ts): TypeScript version of the full workflow, ready for Node.
- [`javascript/load_and_query_sample.ts`](javascript/load_and_query_sample.ts): demonstrates indexing FAQs and issuing targeted prompts.
- Install deps with `npm install` inside `javascript/`, then execute via `npm run start -- path/to/sample.ts`.

## Learn More

- API reference and latest tooling: [docs](https://moss-docs-seven.vercel.app/)
  
If you spot gaps or want another language example, open an issue or PR—we track feedback closely.
