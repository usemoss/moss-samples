<script setup lang="ts">
import { ref, onMounted } from 'vue';

defineProps<{
  text?: string;
}>();

const isMac = ref(false);

onMounted(() => {
  isMac.value =
    typeof navigator !== 'undefined' &&
    /Mac|iPod|iPhone|iPad/.test(navigator.platform);
});
</script>

<template>
  <button
    type="button"
    class="moss-search-btn"
    aria-keyshortcuts="/ control+k meta+k"
    :aria-label="text || 'Search'"
  >
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
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
    <span class="moss-search-btn-text">{{ text || 'Search' }}</span>
    <span class="moss-search-btn-keys">
      <kbd>{{ isMac ? '⌘' : 'Ctrl' }}</kbd><kbd>K</kbd>
    </span>
  </button>
</template>

<style scoped>
.moss-search-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  background: var(--vp-c-bg-alt);
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  cursor: pointer;
  color: var(--vp-c-text-2);
  font-size: 13px;
  transition: border-color 0.2s, color 0.2s;
  white-space: nowrap;
}

.moss-search-btn:hover {
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-text-1);
}

.moss-search-btn-text {
  flex: 1;
}

@media (max-width: 767px) {
  .moss-search-btn-text,
  .moss-search-btn-keys {
    display: none;
  }
}

.moss-search-btn-keys {
  display: flex;
  gap: 2px;
  opacity: 0.6;
}

.moss-search-btn-keys kbd {
  font-family: inherit;
  font-size: 11px;
  padding: 1px 5px;
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-divider);
  border-radius: 3px;
}
</style>
