export interface AuthToken {
  token: string;
  expiresIn: number; // seconds, as returned by the server
}

export interface IAuthenticator {
  getAuthToken(): Promise<AuthToken>;
  getAuthHeader(): Promise<string>; // returns "Bearer <token>"
}
