"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

type BrainMemory = {
  id: string;
  title: string;
  source: string;
  heading: string;
  type: string;
  text: string;
  createdAt: string;
  score?: number;
  tags: string[];
  url?: string;
};

type BrainStats = {
  documents: number;
  sources: number;
  connections: number;
  remembered: number;
  conversations: number;
  tasks: number;
  types: Record<string, number>;
  storagePath: string;
  cloud: boolean;
  localMoss: boolean;
  memoryError?: string;
};

type BrainGraph = {
  nodes: Array<{ id: string; title: string; type: string; chunks: number; degree: number }>;
  edges: Array<{ a: string; b: string; weight: number }>;
};

type BrainView = "memories" | "graph" | "ingest" | "remember";

async function postBrain<T>(body: Record<string, unknown>): Promise<T> {
  const response = await fetch("/api/jarvis", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data?.error || "Second Brain request failed.");
  return data as T;
}

function displayType(type: string) {
  return type.replace(/-/g, " ").toUpperCase();
}

function compactDate(value: string) {
  if (!value) return "ARCHIVE";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value.slice(0, 10) : date.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase();
}

export function SecondBrain({
  open,
  sessionId,
  config,
  onClose,
  onDocumentCount,
}: {
  open: boolean;
  sessionId: string;
  config: Record<string, string>;
  onClose: () => void;
  onDocumentCount: (count: number) => void;
}) {
  const [view, setView] = useState<BrainView>("memories");
  const [memories, setMemories] = useState<BrainMemory[]>([]);
  const [selected, setSelected] = useState<BrainMemory | null>(null);
  const [related, setRelated] = useState<BrainMemory[]>([]);
  const [stats, setStats] = useState<BrainStats | null>(null);
  const [graph, setGraph] = useState<BrainGraph | null>(null);
  const [search, setSearch] = useState("");
  const [type, setType] = useState("all");
  const [recent, setRecent] = useState(false);
  const [sourceFilter, setSourceFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("SECOND BRAIN READY");
  const [url, setUrl] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [rememberText, setRememberText] = useState("");
  const [rememberTitle, setRememberTitle] = useState("");
  const [rememberTags, setRememberTags] = useState("");

  const refreshStats = useCallback(async () => {
    if (!sessionId) return;
    const next = await postBrain<BrainStats>({ action: "brain-stats", sessionId, config });
    setStats(next);
    onDocumentCount(next.documents);
  }, [config, onDocumentCount, sessionId]);

  const runSearch = useCallback(async (override?: { source?: string; query?: string }) => {
    if (!sessionId) return;
    setBusy(true);
    try {
      const nextSource = override?.source ?? sourceFilter;
      const nextQuery = override?.query ?? search;
      const result = await postBrain<{ memories: BrainMemory[]; total: number }>({
        action: nextQuery ? "brain-search" : "brain-list",
        sessionId,
        text: nextQuery,
        source: nextSource || undefined,
        type,
        recent,
        limit: 80,
        config,
      });
      setMemories(result.memories);
      setSelected((current) => result.memories.find((memory) => memory.id === current?.id) || result.memories[0] || null);
      setNotice(`${result.memories.length} MEMORY CHUNKS LOADED`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message.toUpperCase() : "SEARCH FAILED");
    } finally {
      setBusy(false);
    }
  }, [config, recent, search, sessionId, sourceFilter, type]);

  useEffect(() => {
    if (!open || !sessionId) return;
    void Promise.all([runSearch(), refreshStats()]).catch((error) => {
      setNotice(error instanceof Error ? error.message.toUpperCase() : "SECOND BRAIN OFFLINE");
    });
  }, [open, sessionId]); // Initial load is intentionally tied to opening the panel.

  useEffect(() => {
    if (!selected || !sessionId) {
      setRelated([]);
      return;
    }
    let cancelled = false;
    void postBrain<{ related: BrainMemory[] }>({ action: "brain-related", sessionId, memoryId: selected.id, config })
      .then((result) => { if (!cancelled) setRelated(result.related); })
      .catch(() => { if (!cancelled) setRelated([]); });
    return () => { cancelled = true; };
  }, [config, selected?.id, sessionId]);

  async function changeView(next: BrainView) {
    setView(next);
    if (next === "graph" && !graph && sessionId) {
      setBusy(true);
      setNotice("CALCULATING SEMANTIC CONNECTIONS");
      try {
        const result = await postBrain<BrainGraph>({ action: "brain-graph", sessionId, config });
        setGraph(result);
        setNotice(`${result.nodes.length} SOURCES // ${result.edges.length} CONNECTIONS`);
      } catch (error) {
        setNotice(error instanceof Error ? error.message.toUpperCase() : "GRAPH BUILD FAILED");
      } finally {
        setBusy(false);
      }
    }
  }

  async function selectGraphSource(source: string) {
    setSourceFilter(source);
    setSearch("");
    setView("memories");
    await runSearch({ source, query: "" });
  }

  async function submitSearch(event: FormEvent) {
    event.preventDefault();
    await runSearch();
  }

  async function remember(event: FormEvent) {
    event.preventDefault();
    if (!rememberText.trim() || !sessionId) return;
    setBusy(true);
    setNotice("WRITING EPISODIC MEMORY");
    try {
      const result = await postBrain<{ total: number }>({
        action: "brain-remember",
        sessionId,
        text: rememberText,
        title: rememberTitle,
        tags: rememberTags.split(",").map((tag) => tag.trim()).filter(Boolean),
        config,
      });
      setRememberText("");
      setRememberTitle("");
      setRememberTags("");
      setNotice("MEMORY SAVED LOCALLY AND INDEXED");
      onDocumentCount(result.total);
      setGraph(null);
      await Promise.all([runSearch({ query: "", source: "" }), refreshStats()]);
      setView("memories");
    } catch (error) {
      setNotice(error instanceof Error ? error.message.toUpperCase() : "MEMORY WRITE FAILED");
    } finally {
      setBusy(false);
    }
  }

  async function ingest(event: FormEvent) {
    event.preventDefault();
    if ((!url.trim() && !files.length) || !sessionId) return;
    setBusy(true);
    setNotice("INGESTING // CHUNKING // EMBEDDING");
    try {
      const form = new FormData();
      form.set("sessionId", sessionId);
      form.set("config", JSON.stringify(config));
      for (const item of url.split(/\n+/).map((value) => value.trim()).filter(Boolean)) form.append("url", item);
      for (const file of files) form.append("file", file);
      const response = await fetch("/api/jarvis/brain/ingest", { method: "POST", body: form });
      const result = await response.json() as { error?: string; sources?: number; chunks?: number; total?: number; errors?: string[] };
      if (!response.ok) throw new Error(result.error || "Ingestion failed.");
      setUrl("");
      setFiles([]);
      setNotice(`${result.sources} SOURCES // ${result.chunks} CHUNKS INDEXED${result.errors?.length ? ` // ${result.errors.length} SKIPPED` : ""}`);
      onDocumentCount(result.total || 0);
      setGraph(null);
      await Promise.all([runSearch({ query: "", source: "" }), refreshStats()]);
    } catch (error) {
      setNotice(error instanceof Error ? error.message.toUpperCase() : "INGESTION FAILED");
    } finally {
      setBusy(false);
    }
  }

  async function deleteSelected() {
    if (!selected || !sessionId || !window.confirm(`Remove “${selected.title}” from the Second Brain?`)) return;
    setBusy(true);
    try {
      const result = await postBrain<{ total: number }>({ action: "brain-delete", sessionId, memoryId: selected.id, config });
      setSelected(null);
      setRelated([]);
      setGraph(null);
      onDocumentCount(result.total);
      setNotice("MEMORY REMOVED");
      await Promise.all([runSearch(), refreshStats()]);
    } catch (error) {
      setNotice(error instanceof Error ? error.message.toUpperCase() : "DELETE FAILED");
    } finally {
      setBusy(false);
    }
  }

  const types = useMemo(() => Object.keys(stats?.types || {}), [stats]);
  if (!open) return null;

  return (
    <section className="brain-overlay" aria-label="Jarvis Second Brain">
      <div className="brain-grid-noise" />
      <header className="brain-header">
        <div className="brain-title">
          <span className="brain-orb"><i /><i /><b>Ⅱ</b></span>
          <div><small>J.A.R.V.I.S. // COGNITIVE ARCHIVE</small><strong>SECOND BRAIN</strong><em>{notice}</em></div>
        </div>
        <div className="brain-header-stats">
          <span><b>{stats?.documents || 0}</b> CHUNKS</span>
          <span><b>{stats?.sources || 0}</b> SOURCES</span>
          <span><b>{stats?.connections || 0}</b> LINKS</span>
          <span className={stats?.cloud ? "linked" : "local"}><b>{stats?.cloud ? "MOSS" : stats?.localMoss ? "LOCAL MOSS" : "DISK"}</b> MEMORY</span>
        </div>
        <button className="brain-close" onClick={onClose} aria-label="Close Second Brain">×</button>
      </header>

      <nav className="brain-tabs">
        {(["memories", "graph", "ingest", "remember"] as BrainView[]).map((item) => (
          <button key={item} className={view === item ? "active" : ""} onClick={() => void changeView(item)}>
            <span>{item === "memories" ? "⌕" : item === "graph" ? "⌬" : item === "ingest" ? "⇩" : "+"}</span>{item.toUpperCase()}
          </button>
        ))}
        <div className={busy ? "brain-busy active" : "brain-busy"}><i />{busy ? "PROCESSING" : "INDEX STABLE"}</div>
      </nav>

      {view === "memories" && (
        <div className="brain-memory-view">
          <aside className="brain-browser">
            <form className="brain-search" onSubmit={submitSearch}>
              <div><span>⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="SEARCH THE ENTIRE BRAIN..." autoFocus /></div>
              <div className="brain-search-options">
                <select value={type} onChange={(event) => setType(event.target.value)}>
                  <option value="all">ALL MEMORY TYPES</option>
                  {types.map((item) => <option key={item} value={item}>{displayType(item)} ({stats?.types[item]})</option>)}
                </select>
                <label><input type="checkbox" checked={recent} onChange={(event) => setRecent(event.target.checked)} /> PRIORITIZE RECENT</label>
                <button type="submit">SCAN</button>
              </div>
              {sourceFilter && <button type="button" className="source-filter" onClick={() => { setSourceFilter(""); void runSearch({ source: "" }); }}>SOURCE: {sourceFilter} ×</button>}
            </form>
            <div className="brain-memory-list">
              {memories.length === 0 && <p className="brain-empty">NO MEMORY VECTORS MATCH THIS SCAN.</p>}
              {memories.map((memory) => (
                <button key={memory.id} className={selected?.id === memory.id ? "active" : ""} onClick={() => setSelected(memory)}>
                  <span className={`memory-type type-${memory.type}`} />
                  <div><strong>{memory.title}</strong><small>{memory.source}</small></div>
                  <time>{typeof memory.score === "number" ? `${Math.max(0, memory.score).toFixed(3)}` : compactDate(memory.createdAt)}</time>
                </button>
              ))}
            </div>
          </aside>

          <article className="brain-detail">
            {selected ? <>
              <div className="brain-detail-head">
                <div><small>{displayType(selected.type)} // {selected.source}</small><h2>{selected.title}</h2><p>{compactDate(selected.createdAt)}{selected.heading ? ` // ${selected.heading}` : ""}</p></div>
                <button onClick={() => void deleteSelected()}>DELETE VECTOR</button>
              </div>
              <div className="brain-detail-text">{selected.text}</div>
              {selected.tags.length > 0 && <div className="brain-tags">{selected.tags.map((tag) => <span key={tag}>#{tag}</span>)}</div>}
              {selected.url && <a className="brain-source-link" href={selected.url} target="_blank" rel="noreferrer">OPEN ORIGINAL SOURCE ↗</a>}
              <section className="brain-related">
                <div><strong>SEMANTIC NEIGHBORS</strong><small>EMBEDDING-SIMILAR MEMORIES</small></div>
                {related.length === 0 ? <p>NO ADJACENT NODES</p> : related.map((memory) => (
                  <button key={memory.id} onClick={() => { setSelected(memory); if (!memories.some((item) => item.id === memory.id)) setMemories((current) => [memory, ...current]); }}>
                    <span>{typeof memory.score === "number" ? memory.score.toFixed(3) : "LINK"}</span><strong>{memory.title}</strong><small>{memory.source}</small>
                  </button>
                ))}
              </section>
            </> : <div className="brain-empty-detail"><span>Ⅱ</span><strong>SELECT A MEMORY VECTOR</strong><p>Inspect its full contents and traverse related ideas.</p></div>}
          </article>

          <aside className="brain-vitals">
            <section><small>MEMORY TOPOLOGY</small><strong>{stats?.sources || 0}</strong><span>KNOWLEDGE SOURCES</span><i style={{ "--level": `${Math.min(100, (stats?.sources || 0) * 3)}%` } as React.CSSProperties} /></section>
            <section><small>EPISODIC STORE</small><strong>{stats?.remembered || 0}</strong><span>DIRECT MEMORIES</span><i style={{ "--level": `${Math.min(100, (stats?.remembered || 0) * 8)}%` } as React.CSSProperties} /></section>
            <section><small>CONVERSATION ARCHIVE</small><strong>{stats?.conversations || 0}</strong><span>CHAT VECTORS</span><i style={{ "--level": `${Math.min(100, (stats?.conversations || 0) * 2)}%` } as React.CSSProperties} /></section>
            <section className="brain-storage"><small>PERSISTENCE</small><b>{stats?.cloud ? "CLOUD + LOCAL" : stats?.localMoss ? "MOSS LOCAL" : "LOCAL DISK"}</b><p>{stats?.storagePath || "INITIALIZING"}</p></section>
          </aside>
        </div>
      )}

      {view === "graph" && (
        <div className="brain-graph-view">
          <div className="graph-hud"><strong>SEMANTIC CONSTELLATION</strong><span>CLICK A NODE TO OPEN ITS SOURCE // SCROLL TO ZOOM // DRAG TO PAN</span></div>
          {graph ? <BrainGraphCanvas graph={graph} onSelect={(source) => void selectGraphSource(source)} /> : <div className="brain-empty-detail"><strong>BUILDING CONNECTION GRAPH</strong></div>}
        </div>
      )}

      {view === "ingest" && (
        <div className="brain-form-view">
          <section className="brain-form-panel wide">
            <div className="form-kicker">INGESTION MATRIX // MOSS-BRAIN PIPELINE</div>
            <h2>Feed Jarvis your knowledge.</h2>
            <p>Import notes, documents, AI chat exports, web articles, or public YouTube transcripts. Jarvis sanitizes the content, splits it into heading-aware chunks, embeds it locally, and makes it searchable immediately.</p>
            <form onSubmit={ingest}>
              <label className="brain-dropzone">
                <input type="file" multiple accept=".md,.markdown,.txt,.pdf,.docx,.html,.htm,.json,.rst,.org,.csv,.log" onChange={(event) => setFiles(Array.from(event.target.files || []))} />
                <span>⇩</span><strong>SELECT FILES</strong><small>MARKDOWN · TEXT · PDF · DOCX · HTML · AI CHAT EXPORT JSON</small>
                {files.length > 0 && <b>{files.length} FILE{files.length === 1 ? "" : "S"} QUEUED // {(files.reduce((sum, file) => sum + file.size, 0) / 1_048_576).toFixed(1)} MB</b>}
              </label>
              <label className="brain-url-field"><span>PUBLIC LINKS // ONE PER LINE</span><textarea value={url} onChange={(event) => setUrl(event.target.value)} placeholder={'https://example.com/article\nhttps://youtube.com/watch?v=...'} /></label>
              <button className="brain-primary" disabled={busy || (!url.trim() && !files.length)}>INGEST INTO SECOND BRAIN</button>
            </form>
          </section>
          <aside className="brain-capabilities">
            <strong>INGESTION CAPABILITIES</strong>
            {["Heading-aware deterministic chunking", "ChatGPT / Claude / generic export parsing", "PDF and Word text extraction", "Web article cleanup", "Public YouTube transcript capture", "Prompt-role sanitization", "Idempotent source re-import", "Local custom embeddings", "Moss Cloud sync when available"].map((item, index) => <p key={item}><span>{String(index + 1).padStart(2, "0")}</span>{item}</p>)}
          </aside>
        </div>
      )}

      {view === "remember" && (
        <div className="brain-form-view">
          <section className="brain-form-panel">
            <div className="form-kicker">EPISODIC MEMORY // DIRECT WRITE</div>
            <h2>Tell the brain what must persist.</h2>
            <p>Save a decision, preference, deadline, fact, or event without asking the LLM. It becomes searchable in this app and available as context in future Jarvis conversations.</p>
            <form onSubmit={remember}>
              <label><span>MEMORY TITLE // OPTIONAL</span><input value={rememberTitle} onChange={(event) => setRememberTitle(event.target.value)} placeholder="Project launch decision" /></label>
              <label><span>MEMORY CONTENT</span><textarea className="large" value={rememberText} onChange={(event) => setRememberText(event.target.value)} placeholder="We decided to..." required /></label>
              <label><span>TAGS // COMMA SEPARATED</span><input value={rememberTags} onChange={(event) => setRememberTags(event.target.value)} placeholder="project, decision, priority" /></label>
              <button className="brain-primary" disabled={busy || !rememberText.trim()}>COMMIT TO LONG-TERM MEMORY</button>
            </form>
          </section>
          <aside className="brain-capabilities memory-rules">
            <strong>MEMORY PROTOCOL</strong>
            <p><span>01</span>Stored in a private local JSON archive first.</p>
            <p><span>02</span>Indexed through the local Moss SessionIndex.</p>
            <p><span>03</span>Synchronized to your private Moss project when quota permits.</p>
            <p><span>04</span>Recency-aware search can boost fresh memories.</p>
            <p><span>05</span>Jarvis automatically recalls relevant memories before answering.</p>
          </aside>
        </div>
      )}

      <footer className="brain-footer"><span>ADAPTED FROM MOSS-BRAIN // LOCAL-FIRST SEMANTIC MEMORY</span><b>{stats?.memoryError ? "CLOUD DEGRADED // LOCAL SAFE" : "COGNITIVE LINK NOMINAL"}</b></footer>
    </section>
  );
}

function BrainGraphCanvas({ graph, onSelect }: { graph: BrainGraph; onSelect: (source: string) => void }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const parent = canvas.parentElement;
    if (!parent) return;
    const safeCanvas: HTMLCanvasElement = canvas;
    const safeContext: CanvasRenderingContext2D = context;
    const safeParent: HTMLElement = parent;
    const nodes = graph.nodes.map((node, index) => {
      const angle = index * 2.3999632297;
      const radius = 60 + Math.sqrt(index + 1) * 34;
      return { ...node, x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
    });
    const indexById = new Map(nodes.map((node, index) => [node.id, index]));
    let width = 0;
    let height = 0;
    let scale = 0.8;
    let panX = 0;
    let panY = 0;
    let dragging = false;
    let moved = false;
    let lastX = 0;
    let lastY = 0;
    let hover = -1;

    function resize() {
      const rect = safeParent.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      width = rect.width;
      height = rect.height;
      safeCanvas.width = Math.max(1, Math.floor(width * ratio));
      safeCanvas.height = Math.max(1, Math.floor(height * ratio));
      safeCanvas.style.width = `${width}px`;
      safeCanvas.style.height = `${height}px`;
      safeContext.setTransform(ratio, 0, 0, ratio, 0, 0);
      draw();
    }

    function screen(node: { x: number; y: number }) {
      return { x: width / 2 + panX + node.x * scale, y: height / 2 + panY + node.y * scale };
    }

    function draw() {
      safeContext.clearRect(0, 0, width, height);
      safeContext.save();
      safeContext.globalCompositeOperation = "lighter";
      for (const edge of graph.edges) {
        const aIndex = indexById.get(edge.a);
        const bIndex = indexById.get(edge.b);
        if (aIndex === undefined || bIndex === undefined) continue;
        const a = screen(nodes[aIndex]);
        const b = screen(nodes[bIndex]);
        const highlighted = aIndex === hover || bIndex === hover;
        safeContext.strokeStyle = highlighted ? "rgba(145,245,255,.75)" : `rgba(30,183,225,${0.08 + edge.weight * 0.35})`;
        safeContext.lineWidth = highlighted ? 1.6 : Math.max(0.45, edge.weight);
        safeContext.beginPath();
        safeContext.moveTo(a.x, a.y);
        safeContext.lineTo(b.x, b.y);
        safeContext.stroke();
      }
      nodes.forEach((node, index) => {
        const point = screen(node);
        const radius = Math.max(3, Math.min(10, 3 + node.degree * 0.45)) * Math.min(1.35, scale + 0.35);
        const gradient = safeContext.createRadialGradient(point.x, point.y, 0, point.x, point.y, radius * 3);
        gradient.addColorStop(0, index === hover ? "rgba(190,255,255,1)" : "rgba(45,223,255,.95)");
        gradient.addColorStop(0.35, "rgba(22,170,235,.45)");
        gradient.addColorStop(1, "rgba(22,170,235,0)");
        safeContext.fillStyle = gradient;
        safeContext.beginPath();
        safeContext.arc(point.x, point.y, radius * 3, 0, Math.PI * 2);
        safeContext.fill();
        safeContext.fillStyle = index === hover ? "#dfffff" : "#50dcf5";
        safeContext.beginPath();
        safeContext.arc(point.x, point.y, radius, 0, Math.PI * 2);
        safeContext.fill();
        if (index === hover || (scale > 1.2 && node.degree > 3)) {
          safeContext.globalCompositeOperation = "source-over";
          safeContext.fillStyle = "#b9f7ff";
          safeContext.font = "10px SFMono-Regular, monospace";
          safeContext.fillText(node.title.slice(0, 42), point.x + radius + 7, point.y + 3);
          safeContext.globalCompositeOperation = "lighter";
        }
      });
      safeContext.restore();
    }

    function pick(clientX: number, clientY: number) {
      const rect = safeCanvas.getBoundingClientRect();
      const x = clientX - rect.left;
      const y = clientY - rect.top;
      let best = -1;
      let distance = 18;
      nodes.forEach((node, index) => {
        const point = screen(node);
        const next = Math.hypot(point.x - x, point.y - y);
        if (next < distance) { best = index; distance = next; }
      });
      return best;
    }

    const observer = new ResizeObserver(resize);
    observer.observe(safeParent);
    const pointerDown = (event: PointerEvent) => {
      dragging = true;
      moved = false;
      lastX = event.clientX;
      lastY = event.clientY;
      safeCanvas.setPointerCapture(event.pointerId);
    };
    const pointerMove = (event: PointerEvent) => {
      if (dragging) {
        const dx = event.clientX - lastX;
        const dy = event.clientY - lastY;
        if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
        panX += dx;
        panY += dy;
        lastX = event.clientX;
        lastY = event.clientY;
      } else hover = pick(event.clientX, event.clientY);
      draw();
    };
    const pointerUp = (event: PointerEvent) => {
      if (!moved) {
        const selected = pick(event.clientX, event.clientY);
        if (selected >= 0) onSelectRef.current(nodes[selected].id);
      }
      dragging = false;
    };
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      scale = Math.max(0.25, Math.min(3.5, scale * (event.deltaY < 0 ? 1.12 : 0.89)));
      draw();
    };
    safeCanvas.addEventListener("pointerdown", pointerDown);
    safeCanvas.addEventListener("pointermove", pointerMove);
    safeCanvas.addEventListener("pointerup", pointerUp);
    safeCanvas.addEventListener("wheel", wheel, { passive: false });
    resize();
    return () => {
      observer.disconnect();
      safeCanvas.removeEventListener("pointerdown", pointerDown);
      safeCanvas.removeEventListener("pointermove", pointerMove);
      safeCanvas.removeEventListener("pointerup", pointerUp);
      safeCanvas.removeEventListener("wheel", wheel);
    };
  }, [graph]);

  return <canvas ref={canvasRef} className="brain-graph-canvas" />;
}
