# Moss Clustering SDK Examples

Automatically group and organize conversation indexes into meaningful topic-based clusters.

## Examples

### [create-conversation-indexes.ts](./create-conversation-indexes.ts)
Creates a separate Moss index for each conversation JSON file.

### [clustering.ts](./clustering.ts)

Generates topic-based clusters from existing indexes. Demonstrates three methods: manual job control with progress tracking, automatic polling, and one-step convenience method.

### [subset-cluster-example.ts](./subset-cluster-example.ts)

Runs the clustering workflow against a specific subset of indexes. Configure the `MOSS_INDEX_SET` environment variable (comma-separated) to target the desired indexes before execution.

## Setup

### 1. Install Dependencies

```bash
npm install
npm install @inferedge/moss-clustering
```

### 2. Configure Environment

Create `.env` file:

```env
MOSS_PROJECT_ID=your_project_id
MOSS_PROJECT_KEY=your_project_key
```

### 3. Prepare Data

Place conversation JSON files in `data/conversations/`. Each file should contain:

```json
[
  {
    "id": "conv-123-msg-1",
    "text": "Message content here",
    "metadata": {
      "conversation_id": "123",
      "message_number": "1",
      "total_messages": "10"
    }
  }
]
```

## Usage

### Step 1: Create Indexes

Create one index per conversation file:

```bash
npx tsx create-conversation-indexes.ts
```

Output:

```text
Found 115 files

[1/115] conversation-1004371.0.json...
  Created 'conversation-1004371.0' (11 messages)
...
Created: 115
```

### Step 2: Generate Clusters

Group conversations by topic:

```bash
npx tsx clustering.ts
```

Output:

```text
✅ Job started: job_abc123

⏳ Polling for completion...
   [100%] completed

📊 Results: 5 clusters from 113 indexes

1. Delivery Issues (45 indexes)
   Description: Conversations about package delivery problems
   
2. Account Management (32 indexes)
   Description: User account and login related inquiries
...
```

### Optional: Focus Clustering on a Subset

Limit clustering to specific indexes listed in `MOSS_INDEX_SET`:

```bash
export MOSS_INDEX_SET="support-tickets,billing-2024"
npx tsx subset-cluster-example.ts
```

The script deletes any existing clustering run, starts a new job scoped to the provided indexes, and prints progress updates plus a concise cluster summary. Unset `MOSS_INDEX_SET` to fall back to the default demo subset.

## Code Examples

### Create Indexes

```typescript
const indexName = file.replace('.json', '');
await client.createIndex(indexName, documents, 'moss-minilm');
```

### Generate Clusters

#### Option 1: Manual Control (with progress)

```typescript
const job = await clustering.startClusterGeneration(5);

while (true) {
  const { job } = await clustering.getJobStatus(jobResponse.jobId);
  if (job.status === 'completed') break;
  await new Promise(r => setTimeout(r, 7000));
}

const clusters = await clustering.getClusters();
```

#### Option 2: Automatic Polling

```typescript
const result = await clustering.waitForJobCompletion(jobId, 2000);
```

#### Option 3: One-Step (simplest)

```typescript
const result = await clustering.generateClusters(5);
```

## API Reference

### MossClusteringClient

- `startClusterGeneration(numClusters)` - Start job
- `getJobStatus(jobId)` - Check progress
- `waitForJobCompletion(jobId, pollInterval)` - Wait for completion
- `generateClusters(numClusters)` - One-step generation
- `getClusters()` - Get all clusters
- `hasActiveClustering()` - Check if exists
- `deleteClustering()` - Delete clusters

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Missing credentials | Create `.env` with valid credentials |
| No files found | Add JSON files to `data/conversations/` |
| Job failed | Need 20+ indexes for clustering |

## Best Practices

- Use 3-10 clusters depending on data size
- Have 20+ indexes for meaningful results
- Poll every 5-7 seconds
- Always handle job failures

## Requirements

- Node.js 16+
- `@inferedge/moss` SDK
- `@inferedge/moss-clustering` SDK
