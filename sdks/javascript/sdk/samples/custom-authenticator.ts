/**
 * Custom Authenticator Sample
 *
 * Demonstrates how to implement IAuthenticator for use cases where the
 * project key must not be embedded in client-side code — e.g. browser apps,
 * multi-tenant services, or environments that issue short-lived tokens from
 * their own auth system.
 *
 * Pattern: Backend-delegated auth — the client calls your own API to get a
 * Moss token. The project key never leaves your server.
 */

import { MossClient, IAuthenticator, AuthToken, DocumentInfo } from "../src";
import { config } from "dotenv";

config();

// ---------------------------------------------------------------------------
// Backend-delegated authenticator
//
// Your backend holds the project key and issues short-lived Moss tokens to
// authenticated clients on request. The client never sees the project key.
// ---------------------------------------------------------------------------

class BackendDelegatedAuthenticator implements IAuthenticator {
  constructor(
    private readonly tokenEndpoint: string,
    private readonly getRequestHeaders: () => Promise<Record<string, string>>,
  ) {}

  async getAuthToken(): Promise<AuthToken> {
    // Call your own backend endpoint that securely exchanges credentials for a
    // Moss token. The backend calls the Moss identity service with the project
    // key and returns the resulting JWT.
    const headers = await this.getRequestHeaders();
    const response = await fetch(this.tokenEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      signal: AbortSignal.timeout(10_000),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Token endpoint returned HTTP ${response.status}: ${text}`);
    }

    // Your endpoint should return { token: string, expiresIn: number }
    const data = (await response.json()) as { token: string; expiresIn: number };
    return { token: data.token, expiresIn: data.expiresIn };
  }

  async getAuthHeader(): Promise<string> {
    const { token } = await this.getAuthToken();
    return `Bearer ${token}`;
  }
}

// ---------------------------------------------------------------------------
// Demo: use MossClient with a custom authenticator
// ---------------------------------------------------------------------------

async function customAuthenticatorDemo() {
  console.log("Custom Authenticator Demo");

  const projectId = process.env.MOSS_TEST_PROJECT_ID;
  const projectKey = process.env.MOSS_TEST_PROJECT_KEY;

  if (!projectId || !projectKey) {
    console.error("Set MOSS_TEST_PROJECT_ID and MOSS_TEST_PROJECT_KEY in .env");
    return;
  }

  // For the demo we wire up a minimal authenticator backed by the real
  // project key — this mimics what your backend would return to the client.
  const demoAuthenticator: IAuthenticator = {
    async getAuthToken(): Promise<AuthToken> {
      // In a real app this fetch goes to YOUR backend, e.g.:
      //   POST /api/moss-token  →  { token, expiresIn }
      // Here we call the Moss identity service directly to keep the sample
      // self-contained (equivalent to what your backend would do server-side).
      const IDENTITY_URL =
        process.env.MOSS_AUTH_URL ?? "https://service.usemoss.dev/identity/auth/token";
      const response = await fetch(IDENTITY_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ projectId, projectKey }),
        signal: AbortSignal.timeout(10_000),
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(`Auth failed HTTP ${response.status}: ${text}`);
      }

      const data = (await response.json()) as { token: string; expiresIn: number };
      return { token: data.token, expiresIn: data.expiresIn };
    },

    async getAuthHeader(): Promise<string> {
      const { token } = await this.getAuthToken();
      return `Bearer ${token}`;
    },
  };

  // Pass the authenticator instead of a raw project key.
  // The SDK uses it to obtain tokens for every Rust NAPI call.
  const client = new MossClient(projectId, demoAuthenticator);

  const indexName = `custom-auth-demo-${Date.now()}`;
  const docs: DocumentInfo[] = [
    { id: "1", text: "Custom authenticators keep the project key server-side." },
    { id: "2", text: "Short-lived tokens limit the blast radius of a credential leak." },
    { id: "3", text: "The IAuthenticator interface lets you plug in any token source." },
  ];

  try {
    console.log("\n1. Creating index via custom authenticator...");
    const result = await client.createIndex(indexName, docs, { modelId: "moss-minilm" });
    console.log("   Created:", result);

    console.log("\n2. Loading index locally...");
    await client.loadIndex(indexName);

    console.log("\n3. Querying...");
    const results = await client.query(indexName, "keeping credentials safe", { topK: 2 });
    console.log(`   Query: "${results.query}"`);
    results.docs.forEach((doc, i) =>
      console.log(`   ${i + 1}. [score ${doc.score.toFixed(3)}] ${doc.text}`),
    );

    console.log("\n4. Cleaning up...");
    await client.deleteIndex(indexName);
    console.log("   Index deleted.");

    console.log("\nDemo complete.");
  } catch (err) {
    console.error("Error:", err instanceof Error ? err.message : err);
  } finally {
    await client.close();
  }

  // Illustrate constructing a BackendDelegatedAuthenticator — not invoked
  // here since it requires a live backend endpoint.
  const _backendAuth = new BackendDelegatedAuthenticator(
    "https://your-api.example.com/moss-token",
    async () => ({ "X-Session-Token": "user-session-token-here" }),
  );
  console.log("\nBackendDelegatedAuthenticator is ready to use:");
  console.log("  new MossClient(projectId, backendAuth)");
}

export { BackendDelegatedAuthenticator };

customAuthenticatorDemo().catch(console.error);
