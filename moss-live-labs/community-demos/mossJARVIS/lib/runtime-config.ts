export type RuntimeConfig = {
  mossProjectId?: string;
  mossProjectKey?: string;
  mossLongTermIndex?: string;
  openRouterApiKey?: string;
  openRouterModel?: string;
  elevenLabsApiKey?: string;
  elevenLabsVoiceId?: string;
  elevenLabsModelId?: string;
  appUrl?: string;
};

const globalConfig = globalThis as typeof globalThis & {
  __jarvisRuntimeConfig?: RuntimeConfig;
};

const runtimeConfig = globalConfig.__jarvisRuntimeConfig ?? {};
globalConfig.__jarvisRuntimeConfig = runtimeConfig;

export function setRuntimeConfig(input: RuntimeConfig) {
  for (const [key, value] of Object.entries(input)) {
    if (typeof value === "string" && value.trim()) {
      runtimeConfig[key as keyof RuntimeConfig] = value.trim();
    }
  }
}

export function configValue(key: keyof RuntimeConfig, envName: string, fallback = "") {
  return runtimeConfig[key]?.trim() || process.env[envName]?.trim() || fallback;
}

export function configStatus() {
  return {
    moss: Boolean(configValue("mossProjectId", "MOSS_PROJECT_ID") && configValue("mossProjectKey", "MOSS_PROJECT_KEY")),
    openRouter: Boolean(configValue("openRouterApiKey", "OPENROUTER_API_KEY")),
    elevenLabs: Boolean(configValue("elevenLabsApiKey", "ELEVENLABS_API_KEY")),
  };
}

