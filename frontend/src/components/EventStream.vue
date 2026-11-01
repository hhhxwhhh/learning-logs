<script setup>
import { computed } from "vue";
import { bucketOf, countByBucket, filterEvents, relativeTime, clockTime } from "../lib/live";

const props = defineProps({
  events: { type: Array, default: () => [] },
  activeKind: { type: String, default: "all" },
});

defineEmits(["select-kind"]);

const KINDS = [
  { value: "all", label: "全部" },
  { value: "entry", label: "笔记" },
  { value: "session", label: "计时" },
  { value: "card", label: "闪卡" },
  { value: "todo", label: "待办" },
  { value: "topic", label: "主题" },
];

const grouped = computed(() => countByBucket(props.events));
const visible = computed(() => filterEvents(props.events, props.activeKind));
</script>

<template>
  <section class="card">
    <div class="card__head">
      <h3>实时事件</h3>
      <span class="tiny muted">{{ visible.length }} / {{ events.length }} 条</span>
    </div>
    <div class="card__body">
      <div class="filters">
        <button
          v-for="item in KINDS"
          :key="item.value"
          type="button"
          class="chip"
          :class="{ 'chip--on': activeKind === item.value }"
          @click="$emit('select-kind', item.value)"
        >
          {{ item.label }}
          <span v-if="item.value !== 'all' && grouped[item.value]" class="chip__count">
            {{ grouped[item.value] }}
          </span>
        </button>
      </div>

      <ul v-if="visible.length" class="list list--stream">
        <li v-for="event in visible" :key="event.event_id" class="list__item">
          <div class="list__main">
            <span class="list__title">{{ event.summary || event.label }}</span>
            <span class="list__meta">
              <span class="tag tag--{{ bucketOf(event.kind) }}">{{ event.label || event.kind }}</span>
              <span v-if="event.topic">{{ event.topic }}</span>
              <span :title="clockTime(event.created_at)">{{ relativeTime(event.created_at) }}</span>
            </span>
          </div>
        </li>
      </ul>
      <p v-else class="muted small">
        {{ events.length ? "当前筛选下没有事件。" : "还没有事件。去写一条笔记试试。" }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.75rem;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.15rem 0.55rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: transparent;
  color: var(--muted);
  font-size: 0.78rem;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}

.chip:hover {
  border-color: var(--accent);
  color: var(--text);
}

.chip--on {
  border-color: var(--accent);
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}

.chip__count {
  font-size: 0.7rem;
  opacity: 0.7;
}

.list--stream {
  max-height: 22rem;
  overflow-y: auto;
}

.tag {
  padding: 0.05rem 0.4rem;
  border-radius: 4px;
  background: color-mix(in srgb, var(--muted) 16%, transparent);
  font-size: 0.72rem;
}

.tag--entry {
  background: color-mix(in srgb, #3b82f6 18%, transparent);
}

.tag--session {
  background: color-mix(in srgb, #10b981 18%, transparent);
}

.tag--card {
  background: color-mix(in srgb, #f59e0b 18%, transparent);
}

.tag--todo {
  background: color-mix(in srgb, #8b5cf6 18%, transparent);
}

.tag--topic {
  background: color-mix(in srgb, #ec4899 18%, transparent);
}
</style>
