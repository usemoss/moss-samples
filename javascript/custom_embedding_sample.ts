#!/usr/bin/env tsx
/** Custom embeddings workflow sample (TypeScript). */

// ---------- Imports ----------
import { config as loadEnv } from "dotenv";
import { MossClient } from "@inferedge/moss";
import OpenAI from "openai";

loadEnv();

// ---------- Configuration ----------
const MOSS_PROJECT_ID = process.env.MOSS_PROJECT_ID;
const MOSS_PROJECT_KEY = process.env.MOSS_PROJECT_KEY;
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
const MOSS_INDEX_NAME = process.env.MOSS_INDEX_NAME;

if (!MOSS_PROJECT_ID || !MOSS_PROJECT_KEY || !OPENAI_API_KEY || !MOSS_INDEX_NAME) {
	throw new Error(
		"Missing required environment variables. Please set MOSS_PROJECT_ID, MOSS_PROJECT_KEY, OPENAI_API_KEY, and MOSS_INDEX_NAME.",
	);
}

// Fixed: Ensure these are non-null strings for the SDK
const PROJECT_ID = MOSS_PROJECT_ID!;
const PROJECT_KEY = MOSS_PROJECT_KEY!;
const API_KEY = OPENAI_API_KEY!;
const INDEX_NAME = MOSS_INDEX_NAME!;

const mossClient = new MossClient(PROJECT_ID, PROJECT_KEY);
const openaiClient = new OpenAI({ apiKey: API_KEY });

// ---------- Sample Data to create Index ----------
const INITIAL_DOCUMENTS = [
	{
		id: "init-doc-1",
		text: "React is a popular JavaScript library for building user interfaces",
	},
	{
		id: "init-doc-2",
		text: "Python is a versatile programming language used for web development",
	},
	{
		id: "init-doc-3",
		text: "Machine learning enables computers to learn from data",
	},
	{
		id: "init-doc-4",
		text: "Docker containers help package applications with their dependencies",
	},
	{
		id: "init-doc-5",
		text: "TypeScript adds static typing to JavaScript for safer code",
	},
	{
		id: "init-doc-6",
		text: "Kubernetes orchestrates containerized applications at scale",
	},
	{
		id: "init-doc-7",
		text: "GraphQL provides a flexible query language for APIs",
	},
	{
		id: "init-doc-8",
		text: "Redis is an in-memory data store used for caching",
	},
	{
		id: "init-doc-9",
		text: "PostgreSQL is a powerful open-source relational database",
	},
	{
		id: "init-doc-10",
		text: "Git is a distributed version control system for tracking code changes",
	},
];

// ---------- Sample Data to add later ----------
const NEW_DOCUMENTS = [
	{
		id: `step-doc-1`,
		text: "the Pine Grove gardening club meets every Saturday morning to plant herbs",
	},
	{
		id: `step-doc-2`,
		text: "club members water the raised beds and tidy the tool shed after the meeting",
	},
	{
		id: `step-doc-3`,
		text: "organizer Leo keeps a list of herbs to bring for next week",
	},
];

const WORKFLOW_QUERY = "when does the Pine Grove gardening club meet?";

// ---------- Helper Functions ----------
async function generateEmbedding(text: string): Promise<number[]> {
	const response = await openaiClient.embeddings.create({
		model: "text-embedding-3-small",
		input: text,
	});
	return response.data[0]?.embedding ?? [];
}

async function deleteIndex(indexName: string): Promise<void> {
	console.log("🧹 Cleanup: Deleting index...");
	try {
		await mossClient.deleteIndex(indexName);
		console.log(`   ✅ Index "${indexName}" deleted successfully`);
	} catch (error) {
		console.log(`   ⚠️  Failed to delete index "${indexName}": ${String(error)}`);
	}
}

// ---------- Main Workflow ----------
async function main(): Promise<void> {
	console.log("=".repeat(80));
	console.log("🧪 Running Custom Embeddings Workflow Steps");
	console.log("=".repeat(80));
	console.log(`Index: ${INDEX_NAME}`);
	console.log(`Initial documents: ${INITIAL_DOCUMENTS.length}`);
	console.log(`Documents to add later: ${NEW_DOCUMENTS.length}`);
	console.log();

	try {
		console.log("🏗️  Step 0: Creating index with 10 initial documents...");
		console.log("   Generating embeddings for initial documents...");
		const initialDocsWithEmbeddings = await Promise.all(
			INITIAL_DOCUMENTS.map(async (doc) => ({
				...doc,
				embedding: await generateEmbedding(doc.text),
			})),
		);
		console.log(`   ✓ Generated ${initialDocsWithEmbeddings.length} embeddings`);

		console.log("   Creating index with custom embeddings...");
		await mossClient.createIndex(INDEX_NAME, initialDocsWithEmbeddings);
		console.log(`   ✅ Index "${INDEX_NAME}" created successfully with custom embeddings`);
		console.log("   ⏳ Waiting 3 seconds for index to initialize...");
		await new Promise((resolve) => setTimeout(resolve, 3000));
		console.log();

		console.log("📝 Step 1: Generating OpenAI embeddings for new documents...");
		const docsWithEmbeddings = await Promise.all(
			NEW_DOCUMENTS.map(async (doc) => {
				const embedding = await generateEmbedding(doc.text);
				console.log(`   ✓ Generated embedding for "${doc.id}" (dim: ${embedding.length})`);
				return { ...doc, embedding };
			}),
		);
		console.log(`   ✅ Generated ${docsWithEmbeddings.length} embeddings`);
		console.log();

		console.log("📤 Step 2: Adding documents with custom embeddings to index...");
		const addResult = await mossClient.addDocs(INDEX_NAME, docsWithEmbeddings, {
			upsert: true,
		});
		console.log(`   ✅ Job: ${addResult.jobId}, Doc count: ${addResult.docCount}`);
		console.log("   ⏳ Waiting 2 seconds for index to update...");
		await new Promise((resolve) => setTimeout(resolve, 2000));
		console.log();

		console.log("🔍 Step 3: Querying via hotpath (cloud query without loading index)...");
		const queryEmbedding = await generateEmbedding(WORKFLOW_QUERY);
		console.log(`   Generated query embedding (dim: ${queryEmbedding.length})`);

		const hotpathResults = await mossClient.query(INDEX_NAME, WORKFLOW_QUERY, {
			embedding: queryEmbedding,
			topK: 5,
		});

		console.log(`   ✅ Hotpath query returned ${hotpathResults.docs.length} results`);
		console.log(`   Time taken: ${hotpathResults.timeTakenInMs?.toFixed(2)}ms`);
		console.log();
		console.log("   Top 3 results:");
		hotpathResults.docs.slice(0, 3).forEach((doc, index) => {
			console.log(`   ${index + 1}. ${doc.id}`);
			console.log(`      Score: ${doc.score.toFixed(4)}`);
			console.log(`      Text: ${doc.text.substring(0, 60)}...`);
		});

		const newDocPrefixes = NEW_DOCUMENTS.map((doc) => doc.id.split("-").slice(0, 3).join("-"));
		const foundNewDocs = hotpathResults.docs.filter((doc) =>
			newDocPrefixes.some((prefix) => doc.id.startsWith(prefix)),
		);
		console.log(
			`   📊 Found ${foundNewDocs.length} of ${NEW_DOCUMENTS.length} newly added docs in results`,
		);
		console.log();

		console.log("💾 Step 4: Loading index locally...");
		const loadedIndexName = await mossClient.loadIndex(INDEX_NAME);
		console.log(`   ✅ Index "${loadedIndexName}" loaded successfully`);
		console.log();

		console.log("🔎 Step 5: Querying locally (using loaded index)...");
		const localResults = await mossClient.query(INDEX_NAME, WORKFLOW_QUERY, {
			embedding: queryEmbedding,
			topK: 5,
		});

		console.log(`   ✅ Local query returned ${localResults.docs.length} results`);
		console.log(`   Time taken: ${localResults.timeTakenInMs?.toFixed(2)}ms`);
		console.log();
		console.log("   Top 3 results:");
		localResults.docs.slice(0, 3).forEach((doc, index) => {
			console.log(`   ${index + 1}. ${doc.id}`);
			console.log(`      Score: ${doc.score.toFixed(4)}`);
			console.log(`      Text: ${doc.text.substring(0, 60)}...`);
		});

		const foundNewDocsLocal = localResults.docs.filter((doc) =>
			newDocPrefixes.some((prefix) => doc.id.startsWith(prefix)),
		);
		console.log(
			`   📊 Found ${foundNewDocsLocal.length} of ${NEW_DOCUMENTS.length} newly added docs in local results`,
		);
		console.log();

		console.log("🎉 All steps completed successfully!");
		console.log("=".repeat(80));
	} catch (error) {
		console.error();
		console.error("=".repeat(80));
		console.error("❌ STEPS FAILED");
		console.error("=".repeat(80));
		console.error("Error:", error instanceof Error ? error.message : String(error));
		if (error instanceof Error && error.stack) {
			console.error();
			console.error("Stack trace:");
			console.error(error.stack);
		}
		console.error("=".repeat(80));
		throw error;
	} finally {
		console.log();
		await deleteIndex(INDEX_NAME);
	}
}

main().catch((error) => {
	console.error();
	console.error("Fatal error:", error instanceof Error ? error.message : String(error));
	process.exit(1);
});
