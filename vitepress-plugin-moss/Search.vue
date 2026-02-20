<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { useRouter } from 'vitepress';
import SearchButton from './SearchButton.vue';
// @ts-ignore — resolved by the virtual module at build time
import getMossConfig from 'virtual:moss-config';

const config = getMossConfig();

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const isOpen = ref(false);
const query = ref('');
const results = ref<MossResult[]>([]);
const selectedIndex = ref(-1);
const isIndexLoading = ref(false);
const isSearching = ref(false);
const errorMsg = ref('');
const searchInput = ref<HTMLInputElement | null>(null);

interface MossMetadata {
  title: string;
  groupId: string;
  type: 'page' | 'header' | 'text' | 'code';
  groupTitle: string;
  displayBreadcrumb: string;
  sanitizedText: string;
  navigation: string; // the URL to navigate to, including anchor e.g. /guide#installation
}

interface MossResult {
  id: string;
  text: string;
  score?: number;
  metadata?: MossMetadata;
}

// ---------------------------------------------------------------------------
// Moss client
// ---------------------------------------------------------------------------
let mossClient: any = null;
let indexLoaded = false;
let debounceTimer: ReturnType<typeof setTimeout> | null = null;

const loadIndex = async () => {
  if (indexLoaded || isIndexLoading.value) return;
  isIndexLoading.value = true;
  errorMsg.value = '';
  try {
    const { MossClient } = await import('@inferedge/moss');
    mossClient = new MossClient(config.projectId, config.projectKey);
    await mossClient.loadIndex(config.indexName);
    indexLoaded = true;
  } catch (err: any) {
    console.error('[Moss] Failed to load search index:', err);
    errorMsg.value = 'Could not load search index. Check your Moss configuration.';
  } finally {
    isIndexLoading.value = false;
  }
};

// ---------------------------------------------------------------------------
// Open / close
// ---------------------------------------------------------------------------
const open = async () => {
  isOpen.value = true;
  loadIndex(); // fire & forget — UI shows loading state
  await nextTick();
  searchInput.value?.focus();
};

const close = () => {
  isOpen.value = false;
  query.value = '';
  results.value = [];
  selectedIndex.value = -1;
  errorMsg.value = '';
};

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------
const performSearch = async (q: string) => {
  if (!q.trim() || !mossClient || !indexLoaded) {
    results.value = [];
    return;
  }
  isSearching.value = true;
  try {
    const topK = config.search?.topK ?? 10;
    const response = await mossClient.query(config.indexName, q, { topK });
    results.value = response.docs ?? [];
    selectedIndex.value = -1;
  } catch (err) {
    console.error('[Moss] Query error:', err);
    results.value = [];
  } finally {
    isSearching.value = false;
  }
};

watch(query, (q) => {
  if (debounceTimer) clearTimeout(debounceTimer);
  if (!q.trim()) {
    results.value = [];
    selectedIndex.value = -1;
    return;
  }
  debounceTimer = setTimeout(() => performSearch(q), 200);
});

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------
const router = useRouter();

const navigateTo = (result: MossResult) => {
  close();
  // Use metadata.navigation which is the clean URL with anchor, e.g. /guide#installation
  // Fall back to result.id if metadata isn't present
  router.go(result.metadata?.navigation ?? result.id);
};

// ---------------------------------------------------------------------------
// Keyboard handling
// ---------------------------------------------------------------------------
const handleGlobalKeydown = (e: KeyboardEvent) => {
  if (
    (e.key?.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey)) ||
    (!isEditingContent(e) && e.key === '/')
  ) {
    e.preventDefault();
    isOpen.value ? close() : open();
  }
};

const handleModalKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape') {
    close();
  } else if (e.key === 'ArrowDown') {
    e.preventDefault();
    selectedIndex.value = Math.min(selectedIndex.value + 1, results.value.length - 1);
    scrollResultIntoView(selectedIndex.value);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    selectedIndex.value = Math.max(selectedIndex.value - 1, -1);
    scrollResultIntoView(selectedIndex.value);
  } else if (e.key === 'Enter' && selectedIndex.value >= 0) {
    e.preventDefault();
    navigateTo(results.value[selectedIndex.value]);
  }
};

const scrollResultIntoView = (index: number) => {
  if (index < 0) return;
  const el = document.querySelector(`.moss-result[data-index="${index}"]`);
  el?.scrollIntoView({ block: 'nearest' });
};

const isEditingContent = (e: KeyboardEvent): boolean => {
  const el = e.target as HTMLElement;
  return (
    el.isContentEditable ||
    ['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)
  );
};

onMounted(() => window.addEventListener('keydown', handleGlobalKeydown));
onUnmounted(() => window.removeEventListener('keydown', handleGlobalKeydown));

// ---------------------------------------------------------------------------
// Result helpers
// ---------------------------------------------------------------------------
const getTitle = (r: MossResult): string => {
  return r.metadata?.title || r.text.split('\n')[0] || 'Untitled';
};

const getBreadcrumb = (r: MossResult): string => {
  return r.metadata?.displayBreadcrumb ?? '';
};

const getPageTitle = (r: MossResult): string => r.metadata?.groupTitle ?? '';

const getSnippet = (r: MossResult): string => {
  // sanitizedText is the cleaned content without heading prefix
  const s = r.metadata?.sanitizedText ?? '';
  if (s) return s.slice(0, 140);
  // fallback: strip the injected heading line from .text
  const lines = r.text.split('\n').filter(Boolean);
  return lines.slice(2).join(' ').slice(0, 140);
};

const getTypeIcon = (r: MossResult): string => {
  switch (r.metadata?.type) {
    case 'code': return '#';
    case 'header': return '§';
    default: return '';
  }
};
</script>

<template>
  <!-- Nav bar button -->
  <div class="moss-search-wrapper">
    <SearchButton
      :text="config.search?.buttonText || 'Search'"
      :aria-label="config.search?.buttonText || 'Search docs'"
      @click="open"
    />
  </div>

  <!-- Search modal -->
  <Teleport to="body">
    <div
      v-if="isOpen"
      class="moss-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Search"
      @click.self="close"
      @keydown="handleModalKeydown"
    >
      <div class="moss-modal">
        <!-- Header: search input -->
        <div class="moss-header">
          <div class="moss-input-wrap">
            <svg
              class="moss-icon-search"
              xmlns="http://www.w3.org/2000/svg"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              ref="searchInput"
              v-model="query"
              type="search"
              class="moss-input"
              :placeholder="config.search?.placeholder || 'Search docs...'"
              autocomplete="off"
              spellcheck="false"
              @keydown="handleModalKeydown"
            />
            <button
              v-if="query"
              class="moss-btn-clear"
              aria-label="Clear"
              @click="query = ''"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
          <button class="moss-btn-close" aria-label="Close search" @click="close">
            <kbd>Esc</kbd>
          </button>
        </div>

        <!-- Body: status / results -->
        <div class="moss-body">
          <!-- Index loading -->
          <div v-if="isIndexLoading" class="moss-status">
            <svg class="moss-spinner" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M21 12a9 9 0 1 1-6.219-8.56" />
            </svg>
            <span>Loading search index…</span>
          </div>

          <!-- Error -->
          <div v-else-if="errorMsg" class="moss-status moss-status--error">
            <span>{{ errorMsg }}</span>
          </div>

          <!-- No query yet -->
          <div v-else-if="!query.trim()" class="moss-status">
            <span>Type to search the docs</span>
          </div>

          <!-- Searching -->
          <div v-else-if="isSearching" class="moss-status">
            <svg class="moss-spinner" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M21 12a9 9 0 1 1-6.219-8.56" />
            </svg>
            <span>Searching…</span>
          </div>

          <!-- No results -->
          <div v-else-if="results.length === 0" class="moss-status">
            No results for "<strong>{{ query }}</strong>"
          </div>

          <!-- Results -->
          <ul v-else class="moss-results" role="listbox">
            <li
              v-for="(result, i) in results"
              :key="result.id"
              :data-index="i"
              class="moss-result"
              :class="{ 'is-selected': i === selectedIndex }"
              role="option"
              :aria-selected="i === selectedIndex"
              @mouseenter="selectedIndex = i"
              @click="navigateTo(result)"
            >
              <div class="moss-result-header">
                <span v-if="getTypeIcon(result)" class="moss-result-type-icon" aria-hidden="true">{{ getTypeIcon(result) }}</span>
                <span class="moss-result-title">{{ getTitle(result) }}</span>
                <span
                  v-if="getPageTitle(result) && getPageTitle(result) !== getTitle(result)"
                  class="moss-result-page"
                >{{ getPageTitle(result) }}</span>
              </div>
              <div v-if="getBreadcrumb(result)" class="moss-result-breadcrumb">{{ getBreadcrumb(result) }}</div>
              <p v-if="getSnippet(result)" class="moss-result-snippet">
                {{ getSnippet(result) }}
              </p>
            </li>
          </ul>
        </div>

        <!-- Footer -->
        <div class="moss-footer">
          <span class="moss-footer-keys">
            <kbd>↑</kbd><kbd>↓</kbd> navigate &nbsp;
            <kbd>↵</kbd> select &nbsp;
            <kbd>Esc</kbd> close
          </span>
          <span class="moss-footer-brand">
            Search by
            <a href="https://moss.dev" target="_blank" rel="noopener noreferrer">Moss</a>
          </span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* ── Nav wrapper ─────────────────────────────────────────────────────────── */
.moss-search-wrapper {
  display: flex;
  align-items: center;
}

@media (min-width: 768px) {
  .moss-search-wrapper {
    flex-grow: 1;
    padding-left: 24px;
  }
}

@media (min-width: 960px) {
  .moss-search-wrapper {
    padding-left: 32px;
  }
}

/* ── Overlay ─────────────────────────────────────────────────────────────── */
.moss-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(2px);
  z-index: 9999;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 10vh;
}

/* ── Modal ───────────────────────────────────────────────────────────────── */
.moss-modal {
  width: 100%;
  max-width: 640px;
  margin: 0 16px;
  background: var(--vp-c-bg);
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.35);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  max-height: 80vh;
}

/* ── Header ──────────────────────────────────────────────────────────────── */
.moss-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--vp-c-divider);
}

.moss-input-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  padding: 6px 12px;
  transition: border-color 0.2s;
}

.moss-input-wrap:focus-within {
  border-color: var(--vp-c-brand-1);
}

.moss-icon-search {
  color: var(--vp-c-text-3);
  flex-shrink: 0;
}

.moss-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  font-size: 15px;
  color: var(--vp-c-text-1);
  line-height: 1.5;
}

.moss-input::placeholder {
  color: var(--vp-c-text-3);
}

.moss-input::-webkit-search-cancel-button {
  display: none;
}

.moss-btn-clear {
  display: flex;
  align-items: center;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  color: var(--vp-c-text-3);
  transition: color 0.2s;
  line-height: 1;
}

.moss-btn-clear:hover {
  color: var(--vp-c-text-1);
}

.moss-btn-close {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px 6px;
  color: var(--vp-c-text-2);
  border-radius: 5px;
  transition: background 0.15s;
}

.moss-btn-close:hover {
  background: var(--vp-c-bg-soft);
}

.moss-btn-close kbd {
  font-family: inherit;
  font-size: 11px;
  padding: 2px 5px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 3px;
}

/* ── Body ────────────────────────────────────────────────────────────────── */
.moss-body {
  flex: 1;
  overflow-y: auto;
  min-height: 120px;
}

.moss-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 24px;
  color: var(--vp-c-text-2);
  font-size: 14px;
}

.moss-status--error {
  color: var(--vp-c-danger-1, #f43f5e);
}

/* Spinner */
.moss-spinner {
  flex-shrink: 0;
  animation: moss-spin 0.8s linear infinite;
}

@keyframes moss-spin {
  to {
    transform: rotate(360deg);
  }
}

/* ── Results ─────────────────────────────────────────────────────────────── */
.moss-results {
  list-style: none;
  margin: 0;
  padding: 8px;
}

.moss-result {
  padding: 12px 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.12s;
}

.moss-result.is-selected,
.moss-result:hover {
  background: var(--vp-c-bg-soft);
}

.moss-result-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 3px;
}

.moss-result-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--vp-c-brand-1);
  flex-shrink: 0;
}

.moss-result-page {
  font-size: 12px;
  color: var(--vp-c-text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.moss-result-type-icon {
  font-size: 12px;
  color: var(--vp-c-text-3);
  flex-shrink: 0;
}

.moss-result-breadcrumb {
  font-size: 11px;
  color: var(--vp-c-text-3);
  margin-bottom: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.moss-result-snippet {
  margin: 0;
  font-size: 13px;
  color: var(--vp-c-text-2);
  line-height: 1.5;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Footer ──────────────────────────────────────────────────────────────── */
.moss-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-top: 1px solid var(--vp-c-divider);
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.moss-footer-keys kbd {
  font-family: inherit;
  font-size: 11px;
  padding: 1px 4px;
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-divider);
  border-radius: 3px;
}

.moss-footer-brand a {
  color: var(--vp-c-brand-1);
  text-decoration: none;
}

.moss-footer-brand a:hover {
  text-decoration: underline;
}
</style>
