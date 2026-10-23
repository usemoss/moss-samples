# Cross-agent handoff

Move a conversation between agents, channels, or devices without the customer
repeating themselves. Every agent shares one **named session**, so the context
travels with the conversation, not the agent.

```
agent A (chat)   ->  writes the turns, push_index()   ->  cloud
agent B (voice)  ->  session(same name)  ->  resumes, already knows the story
```

## How it works

The first agent opens a session by name, writes the conversation, and pushes it
to the cloud. The second agent, a different process or device, opens the *same*
session name. Because that index already exists, Moss resumes it (no
re-embedding), and the agent can query context it never directly received:

```python
# --- agent A (chat) ---
session = await moss.session(index_name="call-8821")
await session.add_docs([
    DocumentInfo(id="t1", text="Customer reported a duplicate $49.99 charge"),
    DocumentInfo(id="t2", text="Agent confirmed a refund in 3-5 business days"),
])
result = await session.push_index()      # queues a cloud indexing job
await moss.wait_for_job(result.job_id)    # wait until it's ready to resume

# --- agent B (voice, different device) ---
session = await moss.session(index_name="call-8821")   # same name -> resumes
ctx = await session.query("was a refund promised?", QueryOptions(top_k=1))
# ctx.docs[0].text already has the refund promise
```

`push_index()` doesn't finish instantly: it queues server-side processing and
returns a `job_id`. Wait for that job (`wait_for_job`, or poll `get_job_status`)
before another agent resumes the session, otherwise the index may not be ready
to auto-load yet.

The same idea covers chat handing off to voice, a bot escalating to a human, or
a customer moving from phone to laptop. The conversation, the retrieved context,
and the session state all live in one place.

## What you need

- A [Moss](https://moss.dev) account (`MOSS_PROJECT_ID` / `MOSS_PROJECT_KEY`)
- Python 3.10+

## Run

```bash
uv sync                                 # or: pip install moss python-dotenv
cp .env.example .env                    # fill in your keys
uv run python cross_agent_handoff.py    # plain `python` if you used pip
```

Expected: agent A writes three turns and pushes the session; agent B, a fresh
client, resumes the same session by name and answers questions about the charge,
the refund, and the order number, none of which it was told directly.

## Resources

- [Docs](https://docs.moss.dev/?utm_source=github&utm_medium=readme&utm_campaign=cross-agent-handoff)
- [GitHub](https://github.com/usemoss/moss)
