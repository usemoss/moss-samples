import { CLOUD_API_AUTH_URL, env } from "../constants";
import type { IAuthenticator, AuthToken } from "./authenticator.interface";

export class MossServerAuthenticator implements IAuthenticator {
  private readonly authUrl: string;

  constructor(
    private readonly projectId: string,
    private readonly projectKey: string,
  ) {
    this.authUrl = env.MOSS_AUTH_URL ?? CLOUD_API_AUTH_URL;
  }

  async getAuthToken(): Promise<AuthToken> {
    const response = await fetch(this.authUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        projectId: this.projectId,
        projectKey: this.projectKey,
      }),
      signal: AbortSignal.timeout(30_000),
    });

    if (response.status === 401) {
      const text = await response.text();
      throw new Error(`Authentication failed (HTTP 401): ${text}`);
    }

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`HTTP ${response.status}: ${text}`);
    }

    const data = await response.json() as { token: string; expiresIn: number };
    return { token: data.token, expiresIn: data.expiresIn };
  }

  async getAuthHeader(): Promise<string> {
    const { token } = await this.getAuthToken();
    return `Bearer ${token}`;
  }
}
