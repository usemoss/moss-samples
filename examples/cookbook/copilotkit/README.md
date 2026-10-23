# In-App Copilots Grounding — MOSS + CopilotKit

Ground [CopilotKit](https://github.com/CopilotKit/CopilotKit) in-app copilots with MOSS's semantic search runtime (sub-10ms when querying a locally loaded index) to answer user queries using your own knowledge base.

**How it works:**

1. The frontend registers a custom Moss search tool with CopilotKit using a custom React hook `useMossRetrieval`.
2. When the user asks a question in the in-app chatbot, the CopilotKit agent detects if the question requires document retrieval.
3. The agent triggers the retrieval action, sending the query to the browser-side handler.
4. The client queries a secure Next.js API route (`/api/moss/query`), keeping credentials hidden from the browser.
5. The backend uses the Node-based `@moss-dev/moss` SDK to retrieve matching documents from your Moss index.
6. The retrieved documents are fed back to the CopilotKit agent, grounding the LLM's response in accurate, real-time context.

```
You: What is your refund policy?

[Agent triggers Moss search: "refund policy"]
[Moss returns: "Refunds allowed on unused items in original packaging within 30 days..."]

Agent: You can return any unused item in its original packaging within 30 days of purchase for a full refund. Note that return shipping costs are covered by the customer.
```

---

## Project Structure

```
copilotkit/
├── app/
│   ├── api/
│   │   ├── copilotkit/
│   │   │   └── route.ts         # CopilotKit backend runtime orchestrator
│   │   └── moss/
│   │       └── query/
│   │           └── route.ts     # Secure server-side Moss search query endpoint (with mock fallback)
│   ├── globals.css              # Premium dark-mode UI styling
│   ├── layout.tsx               # App root layout with font and style imports
│   ├── page.tsx                 # App entry page with developer dashboard & CopilotChat
│   └── use-moss-retrieval.ts    # React hook mapping the Moss query action to CopilotKit
├── .env.example                 # Environment variables template
├── next.config.ts               # Next.js configurations allowing native Node bindings
├── package.json                 # Project dependencies & scripts
├── README.md                    # This guide
└── tsconfig.json                # TypeScript configurations
```

---

## Setup

### 1. Install dependencies

Install the project dependencies using npm (run in this directory):

```bash
npm install
```

### 2. Set environment variables

Copy the environment variables template and configure your keys:

```bash
cp .env.example .env
```

Open `.env` and fill in the values:

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | **Yes** | Your OpenAI API Key (required by CopilotKit to talk to the LLM agent). |
| `MOSS_PROJECT_ID` | Optional | Your Moss Project ID from the [Moss Portal](https://portal.usemoss.dev). |
| `MOSS_PROJECT_KEY` | Optional | Your Moss Project Key from the [Moss Portal](https://portal.usemoss.dev). |
| `MOSS_INDEX_NAME` | Optional | Name of the Moss index to run queries against. |

> [!NOTE]
> **Mock Mode Fallback:** If you do not provide Moss credentials (`MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY`), the server-side API route will automatically fall back to running query searches against a set of built-in mock documents (Refund Policy, Office Hours, Support Contact, Moss Info). This allows you to explore and test the entire integration end-to-end immediately without needing a Moss account.

---

## Usage

Start the development server:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### What to try:
1. **View the Control Room:** Observe the status badge showing whether the application is running in **Mock Mode** or **Connected to Moss Cloud**.
2. **Interact with the Chat:** Open the chat window on the right side and ask a question such as:
   - *"What is your refund policy?"*
   - *"Where is your corporate headquarters?"*
   - *"How can I contact customer support?"*
   - *"What is Moss?"*
3. **Watch the Retrieval Event Terminal:** As soon as you press send, the **Retrieval Event Terminal** on the bottom-left will stream status updates in real-time, showing the CopilotKit agent calling the Moss search tool and retrieving matching documents.
4. **Test Direct Search:** Use the **Direct Moss Query Sandbox** on the top-left to run queries directly against the Moss API route and inspect the returned documents and confidence scores without calling the LLM.

---

## How MOSS & CopilotKit Handoff Works

### 1. The Hook (`app/use-moss-retrieval.ts`)
The `useMossRetrieval` hook registers the `searchKnowledgeBase` action with CopilotKit using `useCopilotAction`.

```typescript
useCopilotAction({
  name: "searchKnowledgeBase",
  description: "Searches the internal knowledge base to retrieve relevant context...",
  parameters: [
    {
      name: "query",
      type: "string",
      description: "The search query to match against documents.",
      required: true,
    },
  ],
  handler: async ({ query }) => {
    // 1. Triggered when the agent decides it needs knowledge.
    // 2. We perform a client-side fetch to our secure server-side endpoint.
    const response = await fetch(`/api/moss/query?query=${encodeURIComponent(query)}`);
    const data = await response.json();
    
    // 3. Return results back to the agent for grounding.
    return {
      success: true,
      documents: data.docs || [],
    };
  }
});
```

### 2. The Secure Endpoint (`app/api/moss/query/route.ts`)
Queries are executed on the server via `@moss-dev/moss` to prevent exposing secret keys to the browser:

```typescript
import { MossClient } from "@moss-dev/moss";

const mossClient = new MossClient(
  process.env.MOSS_PROJECT_ID,
  process.env.MOSS_PROJECT_KEY
);

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get("query")!;
  const indexName = process.env.MOSS_INDEX_NAME!;
  
  const results = await mossClient.query(indexName, query, { topK: 3 });
  return NextResponse.json({ docs: results.docs });
}
```
