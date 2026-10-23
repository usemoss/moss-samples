# Slack / Discord Q&A bot with Moss

This community demo uses a Moss index containing workspace messages and documents, then answers questions in Slack or Discord using the same retrieval-and-answering pipeline.

The adapters are intentionally thin:

- Slack uses Socket Mode and answers `@mentions` in the originating thread.
- Discord answers `!ask ...` messages or direct bot mentions.
- Moss supplies the relevant workspace context, and an OpenAI-compatible chat model turns that context into a concise answer.

## Setup

1. Create a virtual environment and install the demo:

   ```bash
   uv sync --extra dev
   ```

2. Copy `.env.example` to `.env` and fill in your Moss and OpenAI credentials.

3. Create or load an index named by `MOSS_INDEX_NAME` using the [Moss retrieval workflow](https://docs.moss.dev/docs/integrate/retrieval). Add the messages and documents that the bot should be able to answer from.

4. Configure at least one chat adapter, then start the bot:

   ```bash
   uv run moss-slack-discord
   ```

## Slack configuration

Create a Slack app with Socket Mode enabled, subscribe to the `app_mention` event, and grant the bot permission to read and write messages. Set both `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` in `.env`.

Mention the bot in a channel:

```text
@Workspace Bot What is our refund policy?
```

The answer is posted as a reply in that thread.

## Discord configuration

Create a Discord bot, enable the **Message Content Intent**, and invite it to a server with permission to read and send messages. Set `DISCORD_TOKEN` in `.env`.

Ask a question with the configured prefix or by mentioning the bot:

```text
!ask Where is the onboarding guide?
@Workspace Bot How do I request access?
```

## Tests

The tests cover adapter message extraction and the shared answer engine without requiring chat-platform, Moss, or LLM credentials:

```bash
uv run pytest
```

## Environment variables

| Variable | Purpose |
| --- | --- |
| `MOSS_PROJECT_ID` / `MOSS_PROJECT_KEY` | Moss Cloud credentials |
| `MOSS_INDEX_NAME` | Workspace index to load |
| `MOSS_TOP_K` | Number of Moss results passed to the answerer |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | Answer-generation model configuration |
| `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` | Optional Slack Socket Mode adapter |
| `DISCORD_TOKEN` / `DISCORD_PREFIX` | Optional Discord adapter and command prefix |
