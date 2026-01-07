# Pipecat Quickstart

Build and deploy your first voice AI bot in under 10 minutes. Develop locally, then scale to production on Pipecat Cloud.

**Two steps**: [🏠 Local Development](#run-your-bot-locally) → [☁️ Production Deployment](#deploy-to-production)

## Step 1: Local Development (5 min)

### Prerequisites

#### Environment

- Python 3.10 or later
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager installed

#### AI Service API keys

You'll need API keys from four services:

- [Moss](https://portal.usemoss.dev) for semantic retrieval
- [Deepgram](https://console.deepgram.com/signup) for Speech-to-Text
- [OpenAI](https://auth.openai.com/create-account) for LLM inference
- [Cartesia](https://play.cartesia.ai/sign-up) for Text-to-Speech

> 💡 **Tip**: Sign up for all four now. You'll need them for both local and cloud deployment.

### Setup

Navigate to the quickstart directory and set up your environment.

1. Clone this repository

   ```bash
   git clone https://github.com/usemoss/moss-samples.git
   cd pipecat-moss/pipecat-quickstart/
   ```

2. Configure your API keys:

   Create a `.env` file:

   ```bash
   cp env.example .env
   ```

   Then, add your API keys:

   ```ini
   MOSS_PROJECT_ID=your_moss_project_id
   MOSS_PROJECT_KEY=your_moss_project_key
   MOSS_INDEX_NAME=your_moss_index_name

   DEEPGRAM_API_KEY=your_deepgram_api_key
   OPENAI_API_KEY=your_openai_api_key
   CARTESIA_API_KEY=your_cartesia_api_key
   ```

3. Set up a virtual environment and install dependencies

   ```bash
   uv sync
   source .venv/bin/activate # Activate the virtual environment
   ```

### Upload your Moss index:

Before running the bot, ensure your Moss index is uploaded. Use the provided script:

```bash
uv run create-index.py
```

### Run your bot locally

```bash
uv run bot.py
```

**Open http://localhost:7860 in your browser** and click `Connect` to start talking to your bot.

> 💡 First run note: The initial startup may take ~20 seconds as Pipecat downloads required models and imports.

🎉 **Success!** Your bot is running locally. Now let's deploy it to production so others can use it.

---

## Integrate Moss Semantic Retrieval

Moss delivers sub-10ms semantic retrieval, so your Pipecat voice agent can respond with relevant knowledge without adding latency.

### Install the integration

If you are bringing your own environment, install it manually:

```bash
pip install pipecat-moss
```
### Load Moss in the Pipecat pipeline

`bot.py` wires `MossRetrievalService` into the Pipecat pipeline so retrieved passages reach the LLM:

```python
from pipecat_moss import MossRetrievalService

moss_service = MossRetrievalService(
    project_id=os.getenv("MOSS_PROJECT_ID"),
    project_key=os.getenv("MOSS_PROJECT_KEY"),
    system_prompt="Relevant passages from the Moss knowledge base:\n\n",
)

async def initialize_moss_index():
    await moss_service.load_index(os.getenv("MOSS_INDEX_NAME"))

# Call the initialization function
await initialize_moss_index()

pipeline = Pipeline([
    transport.input(),
    stt,
    context_aggregator.user(),
    moss_service.query(os.getenv("MOSS_INDEX_NAME"), top_k=5),
    llm,
    tts,
    transport.output(),
    context_aggregator.assistant(),
])
```
### Configuration options

`MossRetrievalService` accepts:

- `project_id` and `project_key`: Moss credentials
- `system_prompt`: Prefix appended ahead of retrieved passages
- `load_index(index_name)`: Awaitable loader for the index your bot should query
- `query(index_name, *, top_k=5, alpha=0.8)`: Returns a processor that retrieves result; top_k controls number of passages, alpha blends semantic and keyword scores

### Compatibility and support

- Tested with Pipecat `v0.0.94` and newer
- [Support for Pipecat-Moss](https://github.com/usemoss/pipecat-moss).
- [Moss docs](https://docs.usemoss.dev)
- [Moss Discord](https://discord.com/invite/eMXExuafBR)


## Step 2: Deploy to Production (5 min)

Transform your local bot into a production-ready service. Pipecat Cloud handles scaling, monitoring, and global deployment.

### Prerequisites

1. [Sign up for Pipecat Cloud](https://pipecat.daily.co/sign-up).

2. Set up Docker for building your bot image:

   - **Install [Docker](https://www.docker.com/)** on your system
   - **Create a [Docker Hub](https://hub.docker.com/) account**
   - **Login to Docker Hub:**

     ```bash
     docker login
     ```

3. Install the Pipecat CLI

   ```bash
   uv tool install pipecat-ai-cli
   ```

   > Tip: You can run the `pipecat` CLI using the `pc` alias.

### Configure your deployment

The `pcc-deploy.toml` file tells Pipecat Cloud how to run your bot. **Update the image field** with your Docker Hub username by editing `pcc-deploy.toml`.

```ini
agent_name = "quickstart"
image = "YOUR_DOCKERHUB_USERNAME/quickstart:0.1"  # 👈 Update this line
secret_set = "quickstart-secrets"

[scaling]
	min_agents = 1
```

**Understanding the TOML file settings:**

- `agent_name`: Your bot's name in Pipecat Cloud
- `image`: The Docker image to deploy (format: `username/image:version`)
- `secret_set`: Where your API keys are stored securely
- `min_agents`: Number of bot instances to keep ready (1 = instant start)

> 💡 Tip: [Set up `image_credentials`](https://docs.pipecat.ai/deployment/pipecat-cloud/fundamentals/secrets#image-pull-secrets) in your TOML file for authenticated image pulls

### Log in to Pipecat Cloud

To start using the CLI, authenticate to Pipecat Cloud:

```bash
pipecat cloud auth login
```

You'll be presented with a link that you can click to authenticate your client.

### Configure secrets

Upload your API keys to Pipecat Cloud's secure storage:

```bash
pipecat cloud secrets set quickstart-secrets --file .env
```

This creates a secret set called `quickstart-secrets` (matching your TOML file) and uploads all your API keys from `.env`.

### Build and deploy

Build your Docker image and push to Docker Hub:

```bash
pipecat cloud docker build-push
```

Deploy to Pipecat Cloud:

```bash
pipecat cloud deploy
```

### Connect to your agent

1. Open your [Pipecat Cloud dashboard](https://pipecat.daily.co/)
2. Select your `quickstart` agent → **Sandbox**
3. Allow microphone access and click **Connect**

---

## What's Next?

**🔧 Customize your bot**: Modify `bot.py` to change personality, add functions, or integrate with your data  
**📚 Learn more**: Check out [Pipecat's docs](https://docs.pipecat.ai/) for advanced features  
**💬 Get help**: Join [Pipecat's Discord](https://discord.gg/pipecat) to connect with the community

### Troubleshooting

- **Browser permissions**: Allow microphone access when prompted
- **Connection issues**: Try a different browser or check VPN/firewall settings
- **Audio issues**: Verify microphone and speakers are working and not muted
