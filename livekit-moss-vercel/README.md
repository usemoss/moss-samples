# LiveKit Voice Agent with Moss Search

This example demonstrates a real-time voice agent built with [LiveKit](https://livekit.io) and [Moss](https://usemoss.dev). The agent listens to user queries, searches a Moss FAQ index for relevant answers, and responds using an LLM—all with low latency suitable for voice interactions.

The project consists of two parts:
1. **`livekit-voice-agent`**: The backend Python agent that handles voice processing, LLM interaction, and Moss queries.
2. **`agent-react`**: A Next.js frontend that connects to the LiveKit room and provides the UI.

## Prerequisites

- **Moss Account**: Sign up at [usemoss.dev](https://usemoss.dev) and create a project. You'll need your `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY`.
- **LiveKit Cloud**: Sign up for [LiveKit Cloud](https://cloud.livekit.io/) to get your URL and API Keys.
- **API Keys**:
  - OpenAI (for LLM)
  - Deepgram (for STT)
  - Cartesia (for TTS)

## Setup

### 1. Backend Setup (`livekit-voice-agent`)

Navigate to the agent directory:

```bash
cd livekit-moss-vercel/livekit-voice-agent/livekit-moss-agent
```

Install dependencies (we recommend using `uv` or a virtual environment):

```bash
uv sync
```

Create a `.env.local` file in `livekit-moss-agent/` with the following variables:

```bash
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_livekit_key
LIVEKIT_API_SECRET=your_livekit_secret

OPENAI_API_KEY=your_openai_key
DEEPGRAM_API_KEY=your_deepgram_key
CARTESIA_API_KEY=your_cartesia_key

MOSS_PROJECT_ID=your_moss_project_id
MOSS_PROJECT_KEY=your_moss_project_key
MOSS_INDEX_NAME=voice-agent-faqs
```

**Seed the Moss Index:**

Before running the agent, upload the FAQ data to Moss:

```bash
python create_index.py
```

**Run the Agent:**

Start the agent in development mode:

```bash
python agent.py dev
```

The agent is now waiting for a user to connect to the LiveKit room.

### 2. Frontend Setup (`agent-react`)

Open a new terminal and navigate to the frontend directory:

```bash
cd agent-react
```

Install dependencies:

```bash
pnpm install
```

Create a `.env.local` file with your LiveKit credentials (these generate tokens for the client):

```bash
LIVEKIT_API_KEY=your_livekit_key
LIVEKIT_API_SECRET=your_livekit_secret
LIVEKIT_URL=wss://your-project.livekit.cloud
```

Start the development server:

```bash
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser. Click "Connect" to join the room and start talking to the agent!

## How it Works

1. **Voice Input**: The user speaks into the frontend; LiveKit streams audio to the Python agent.
2. **Transcription**: Deepgram converts speech to text.
3. **Intent Check**: The agent checks if the user's query requires knowledge lookup.
4. **Moss Search**: If needed, the agent calls `search_support_faqs`, which queries the Moss index for relevant context.
5. **LLM Response**: OpenAI GPT-4o (or configured model) generates a response using the retrieved context.
6. **Voice Output**: Cartesia converts the text response back to speech, streamed to the user.

