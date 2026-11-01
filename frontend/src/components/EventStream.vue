<script setup>
defineProps({
  events: { type: Array, default: () => [] },
});

function clock(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}
</script>

<template>
  <section class="card">
    <div class="card__head">
      <h3>实时事件</h3>
      <span class="tiny muted">{{ events.length }} 条</span>
    </div>
    <div class="card__body">
      <ul v-if="events.length" class="list">
        <li v-for="event in events" :key="event.event_id" class="list__item">
          <div class="list__main">
            <span class="list__title">{{ event.summary || event.label }}</span>
            <span class="list__meta">
              <span>{{ event.label || event.kind }}</span>
              <span v-if="event.topic">{{ event.topic }}</span>
              <span>{{ clock(event.created_at) }}</span>
            </span>
          </div>
        </li>
      </ul>
      <p v-else class="muted small">还没有事件。去写一条笔记试试。</p>
    </div>
  </section>
</template>
