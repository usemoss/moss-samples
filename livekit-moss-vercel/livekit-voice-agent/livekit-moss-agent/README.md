# Moss LiveKit Voice Agent

This directory contains a high-performance voice AI agent built with [LiveKit Agents](https://docs.livekit.io/agents) and [Moss](https://usemoss.dev) for real-time semantic retrieval.

The agent acts as a customer support assistant, fetching relevant information from a knowledge base indexed in Moss to provide accurate and low-latency responses.

## 📋 Prerequisites

- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** (recommended package manager)
- **LiveKit Cloud account** (or local LiveKit server)
- **Moss account** (from [portal.usemoss.dev](https://portal.usemoss.dev))
- **AI Service Keys**: OpenAI (LLM), Deepgram (STT), and Cartesia (TTS).

## ⚙️ Setup

1. **Configure Environment Variables**:
   Copy the template and fill in your credentials in a new `.env.local` file:

   ```bash
   cp .env.template .env.local
   ```

   Required variables:
   - `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
   - `MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY`, `MOSS_INDEX_NAME`
   - `OPENAI_API_KEY`
   - `DEEPGRAM_API_KEY`
   - `CARTESIA_API_KEY`

2. **Install Dependencies**:
   ```bash
   uv sync
   ```

## 🚀 Usage

### 1. Index Your Data

Before running the agent, upload your FAQ documents to Moss:

```bash
uv run create_index.py
```

This script reads `faqs.json` and creates a semantic index in your Moss project.

### 2. Run the Agent

Start the agent in development mode:

```bash
uv run agent.py dev
```

The agent will connect to your LiveKit project and wait for users to join a room.

## 🧪 Testing Locally

Once the agent is running (`uv run agent.py dev`), you can interact with it using one of these methods:

### Option A: LiveKit Agents Playground (Easiest)

1. Go to the [LiveKit Cloud Console](https://cloud.livekit.io/).
2. Select your project.
3. Click on the **Agents** tab and then **Playground**.
4. Click **Connect** to start a session. Your local agent should automatically join and start talking!

### Option B: Local React Frontend

We have a pre-built React frontend in the sibling directory:

1. Open a new terminal and navigate to `../../agent-react`.
2. Follow its README to set up and run:
   ```bash
   pnpm install
   pnpm dev
   ```
3. Open `http://localhost:3000` and click **Connect**.

---

## 🛠️ Integration Details

- **Retrieval**: Uses `MossClient` to perform sub-10ms semantic lookups.
- **Tools**: The agent is equipped with a `search_support_faqs` function tool that the LLM can call whenever it needs context from the knowledge base.
- **Voice Pipeline**:
  - **STT**: Deepgram Nova-2
  - **LLM**: OpenAI GPT-5
  - **TTS**: Cartesia Sonic-2

## 📦 Deployment

To deploy this agent to production, you can use the provided `Dockerfile` or deploy directly to **LiveKit Cloud**.

For a full stack example including a React frontend, see the root `livekit-moss-vercel` directory.
