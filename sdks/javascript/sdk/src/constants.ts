import * as MossCore from "@moss-js/moss-core";

const rustCore = MossCore as unknown as {
  MODEL_DOWNLOAD_URL: string;
  SDK_VERSION_NUMBER: string;
  CLOUD_API_IDENTITY_URL: string;
  CLOUD_API_AUTH_URL: string;
  CLOUD_API_INDEX_URL: string;
};

export const MODEL_DOWNLOAD_URL = rustCore.MODEL_DOWNLOAD_URL;
export const SDK_VERSION_NUMBER = rustCore.SDK_VERSION_NUMBER;

/** Base URL for the Moss identity service. */
export const CLOUD_API_IDENTITY_URL = rustCore.CLOUD_API_IDENTITY_URL;

/** Auth token endpoint for MossServerAuthenticator. */
export const CLOUD_API_AUTH_URL = rustCore.CLOUD_API_AUTH_URL;

/** Base URL for the Moss index management service. */
export const CLOUD_API_INDEX_URL =
  (typeof process !== "undefined" && process.env.MOSS_INDEX_URL) ||
  rustCore.CLOUD_API_INDEX_URL;

/** process.env wrapper — allows MossServerAuthenticator to read MOSS_AUTH_URL override. */
export const env = (typeof process !== "undefined" ? process.env : {}) as {
  MOSS_AUTH_URL?: string;
};
