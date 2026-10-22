import { createHash } from "node:crypto";
import { lookup } from "node:dns/promises";
import net from "node:net";

export type BrainSource = {
  source: string;
  title: string;
  text: string;
  kind: "note" | "document" | "conversation" | "web" | "youtube";
  url?: string;
};

export type BrainChunk = {
  id: string;
  text: string;
  metadata: Record<string, unknown>;
};

const SANITIZE_PATTERNS: Array<[RegExp, string]> = [
  [/<\|im_(?:start|end)\|>/gi, " "],
  [/<\|(?:user|assistant|system)\|>/gi, " "],
  [/\[\/?INST\]|<<SYS>>|<<\/SYS>>/gi, " "],
  [/<tool\s+name="[^"]*">|<\/tool>|<\/?chat>/gi, " "],
  [/^\s*human\s*:/gim, "Q:"],
  [/^\s*assistant\s*:/gim, "A:"],
];

export function sanitizeBrainText(value: string) {
  return SANITIZE_PATTERNS.reduce((text, [pattern, replacement]) => text.replace(pattern, replacement), value)
    .replace(/\u0000/g, "")
    .trim();
}

function stableId(value: string) {
  return createHash("md5").update(value).digest("hex").slice(0, 16);
}

export function chunkBrainSource(source: BrainSource, importedAt = new Date().toISOString()): BrainChunk[] {
  const sections: Array<{ heading: string; lines: string[] }> = [{ heading: "", lines: [] }];
  for (const line of source.text.split(/\r?\n/)) {
    if (/^#{1,6}\s+/.test(line)) {
      sections.push({ heading: line.replace(/^#{1,6}\s+/, "").trim(), lines: [] });
    } else {
      sections.at(-1)?.lines.push(line);
    }
  }

  const chunks: BrainChunk[] = [];
  for (const [sectionIndex, section] of sections.entries()) {
    const body = section.lines.join("\n").trim();
    if (!body) continue;
    const parts = body.match(/[\s\S]{1,3600}(?:\n\n|$)|[\s\S]{1,3600}/g) || [body];
    for (const [partIndex, part] of parts.entries()) {
      const headingSuffix = section.heading ? ` — ${section.heading}` : "";
      const text = sanitizeBrainText(`[${source.source}${headingSuffix}]\n${section.heading ? `${section.heading}\n` : ""}${part}`)
        .slice(0, 4000);
      if (text.length < 20) continue;
      chunks.push({
        id: `brain-${stableId(`${source.source}#${sectionIndex}#${partIndex}`)}`,
        text,
        metadata: {
          type: source.kind === "conversation" ? "conversation-archive" : "knowledge",
          source: source.source,
          title: source.title,
          heading: section.heading,
          sourceKind: source.kind,
          url: source.url,
          chunkIndex: chunks.length,
          importedAt,
          createdAt: importedAt,
        },
      });
    }
  }
  return chunks;
}

function slug(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 72) || "untitled";
}

function textFromMessage(message: Record<string, unknown>) {
  const candidates = [message.content, message.text, message.message, message.parts, message.body, message.value];
  for (let value of candidates) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const object = value as Record<string, unknown>;
      value = object.text ?? object.parts ?? object.content;
    }
    if (Array.isArray(value)) {
      const joined = value.map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") return String((item as Record<string, unknown>).text || "");
        return "";
      }).filter(Boolean).join("\n");
      if (joined.trim()) return joined.trim();
    }
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function roleFromMessage(message: Record<string, unknown>) {
  for (const key of ["role", "sender", "author", "from", "speaker"]) {
    let value = message[key];
    if (value && typeof value === "object") {
      const object = value as Record<string, unknown>;
      value = object.role ?? object.name;
    }
    if (typeof value === "string" && value) return value.toLowerCase();
  }
  return "";
}

function genericChatExport(data: unknown, vendor: string): BrainSource[] {
  const conversations: Array<{ title: string; messages: Array<{ role: string; text: string }> }> = [];
  const seen = new Set<unknown>();

  function asMessages(value: unknown) {
    const items = value && typeof value === "object" && !Array.isArray(value)
      ? Object.values(value as Record<string, unknown>)
      : value;
    if (!Array.isArray(items) || !items.length) return null;
    const messages = items.flatMap((item) => {
      const object = item && typeof item === "object" ? item as Record<string, unknown> : null;
      const nested = object?.message && typeof object.message === "object" ? object.message as Record<string, unknown> : object;
      if (!nested) return [];
      const role = roleFromMessage(nested);
      const text = textFromMessage(nested);
      return role && text ? [{ role, text }] : [];
    });
    return messages.some((message) => ["user", "human"].includes(message.role)) ? messages : null;
  }

  function walk(value: unknown, title = "") {
    if (!value || typeof value !== "object" || seen.has(value)) return;
    seen.add(value);
    if (Array.isArray(value)) {
      const messages = asMessages(value);
      if (messages) conversations.push({ title, messages });
      else value.forEach((item) => walk(item, title));
      return;
    }
    const object = value as Record<string, unknown>;
    const nextTitle = typeof object.title === "string" ? object.title : typeof object.name === "string" ? object.name : title;
    for (const [key, child] of Object.entries(object)) {
      if (["messages", "chat_messages", "conversation", "history", "chats", "mapping"].includes(key)) {
        const messages = asMessages(child);
        if (messages) {
          conversations.push({ title: nextTitle, messages });
          continue;
        }
      }
      walk(child, nextTitle);
    }
  }

  walk(data);
  return conversations.map((conversation, index) => {
    const title = conversation.title || `Conversation ${index + 1}`;
    const text = [`# ${title}`, "", ...conversation.messages.map((message) =>
      `${["user", "human"].includes(message.role) ? "Q" : "A"}: ${message.text}`)].join("\n");
    return {
      source: `${vendor}/${slug(title)}-${index + 1}`,
      title,
      text,
      kind: "conversation" as const,
    };
  }).filter((source) => source.text.length > 150);
}

function decodeEntities(value: string) {
  const entities: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: "\"", apos: "'", nbsp: " " };
  return value.replace(/&(#x?[0-9a-f]+|[a-z]+);/gi, (_, entity: string) => {
    if (entity.startsWith("#x")) return String.fromCodePoint(Number.parseInt(entity.slice(2), 16));
    if (entity.startsWith("#")) return String.fromCodePoint(Number.parseInt(entity.slice(1), 10));
    return entities[entity.toLowerCase()] ?? `&${entity};`;
  });
}

function readableHtml(html: string) {
  const title = decodeEntities(html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1]?.replace(/<[^>]+>/g, " ") || "Web article").trim();
  const text = decodeEntities(html
    .replace(/<(script|style|nav|footer|header|aside|form|svg)\b[^>]*>[\s\S]*?<\/\1>/gi, " ")
    .replace(/<(br|p|div|section|article|h[1-6]|li)\b[^>]*>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n"));
  return { title, text: text.trim() };
}

function isPrivateHost(hostname: string) {
  const host = hostname.toLowerCase();
  if (host === "localhost" || host.endsWith(".localhost") || host === "::1") return true;
  if (net.isIP(host) === 4) {
    const [a, b] = host.split(".").map(Number);
    return a === 10 || a === 127 || a === 0 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
  }
  if (net.isIP(host) === 6) return host === "::1" || host.startsWith("fc") || host.startsWith("fd") || host.startsWith("fe8") || host.startsWith("fe9") || host.startsWith("fea") || host.startsWith("feb");
  return false;
}

async function assertPublicUrl(url: URL) {
  if (!["http:", "https:"].includes(url.protocol) || isPrivateHost(url.hostname)) throw new Error("Only public HTTP(S) links can be ingested.");
  const addresses = await lookup(url.hostname, { all: true });
  if (!addresses.length || addresses.some(({ address }) => isPrivateHost(address))) throw new Error("That link resolves to a private network address.");
}

async function fetchPublicPage(initialUrl: URL) {
  let current = initialUrl;
  for (let redirects = 0; redirects <= 5; redirects += 1) {
    await assertPublicUrl(current);
    const response = await fetch(current, {
      headers: { "user-agent": "Jarvis-Second-Brain/1.0" },
      redirect: "manual",
      signal: AbortSignal.timeout(30_000),
    });
    if (![301, 302, 303, 307, 308].includes(response.status)) return response;
    const location = response.headers.get("location");
    if (!location) throw new Error("The link redirected without a destination.");
    current = new URL(location, current);
  }
  throw new Error("The link redirected too many times.");
}

async function fetchUrl(urlValue: string): Promise<BrainSource> {
  const url = new URL(urlValue);
  await assertPublicUrl(url);
  const youtube = url.hostname.replace(/^www\./, "").match(/^(youtube\.com|youtu\.be)$/)
    ? (url.hostname.includes("youtu.be") ? url.pathname.slice(1) : url.searchParams.get("v") || url.pathname.split("/").filter(Boolean).at(-1))
    : null;
  if (youtube && /^[\w-]{11}$/.test(youtube)) {
    const [metaResponse, transcriptResponse] = await Promise.all([
      fetch(`https://www.youtube.com/oembed?url=${encodeURIComponent(url.toString())}&format=json`, { signal: AbortSignal.timeout(20_000) }),
      fetch(`https://www.youtube.com/api/timedtext?v=${youtube}&lang=en`, { signal: AbortSignal.timeout(20_000) }),
    ]);
    const metadata = metaResponse.ok ? await metaResponse.json() as { title?: string } : {};
    const transcriptXml = transcriptResponse.ok ? await transcriptResponse.text() : "";
    const transcript = decodeEntities([...transcriptXml.matchAll(/<text[^>]*>([\s\S]*?)<\/text>/g)].map((match) => match[1].replace(/<[^>]+>/g, " ")).join(" "));
    if (!transcript.trim()) throw new Error("No public English transcript was available for this YouTube video.");
    const title = metadata.title || youtube;
    return { source: `youtube/${slug(title)}`, title, text: `# ${title}\n\n${transcript}`, kind: "youtube", url: url.toString() };
  }

  const response = await fetchPublicPage(url);
  if (!response.ok) throw new Error(`Link returned HTTP ${response.status}.`);
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("text/html") && !contentType.includes("text/plain")) throw new Error("This link is not a readable text page.");
  const raw = await response.text();
  const readable = contentType.includes("html") ? readableHtml(raw) : { title: url.hostname, text: raw };
  return { source: `web/${slug(readable.title)}`, title: readable.title, text: `# ${readable.title}\n(${url})\n\n${readable.text}`, kind: "web", url: url.toString() };
}

export async function sourceFromUrl(url: string) {
  return fetchUrl(url.trim());
}

export async function sourceFromFile(file: File): Promise<BrainSource[]> {
  const extension = file.name.toLowerCase().split(".").at(-1) || "";
  const base = file.name.replace(/\.[^.]+$/, "");
  const buffer = Buffer.from(await file.arrayBuffer());
  if (extension === "pdf") {
    const pdf = (await import("pdf-parse")).default;
    const parsed = await pdf(buffer);
    return [{ source: `documents/${slug(base)}`, title: base, text: `# ${base}\n\n${parsed.text}`, kind: "document" }];
  }
  if (extension === "docx") {
    const mammoth = await import("mammoth");
    const parsed = await mammoth.extractRawText({ buffer });
    return [{ source: `documents/${slug(base)}`, title: base, text: `# ${base}\n\n${parsed.value}`, kind: "document" }];
  }
  const text = buffer.toString("utf8");
  if (extension === "json") {
    const sources = genericChatExport(JSON.parse(text) as unknown, slug(base));
    if (sources.length) return sources;
    throw new Error(`${file.name} did not contain a recognized conversation export.`);
  }
  if (["html", "htm"].includes(extension)) {
    const readable = readableHtml(text);
    return [{ source: `documents/${slug(base)}`, title: readable.title || base, text: `# ${readable.title || base}\n\n${readable.text}`, kind: "document" }];
  }
  if (!["md", "markdown", "txt", "rst", "org", "csv", "log"].includes(extension)) {
    throw new Error(`${file.name} is not a supported brain source.`);
  }
  return [{ source: `notes/${slug(base)}`, title: base, text: text.startsWith("#") ? text : `# ${base}\n\n${text}`, kind: "note" }];
}
