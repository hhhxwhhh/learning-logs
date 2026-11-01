<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import MetricCards from "./components/MetricCards.vue";
import EventStream from "./components/EventStream.vue";
import TrendChart from "./components/TrendChart.vue";

const props = defineProps({
  initial: { type: Object, default: () => ({}) },
  wsUrl: { type: String, default: "/ws/live/" },
});

const status = ref("connecting");
const events = ref(props.initial.events || []);
const metrics = ref({ ...(props.initial.metrics || {}) });
const series = ref(props.initial.series || []);
const activeKind = ref("all");
let socket = null;
let retry = null;
let attempts = 0;

const statusText = computed(() => {
  if (status.value === "open") return "已连接";
  if (status.value === "closed") return "连接断开，正在重连";
  return "连接中";
});

function endpoint() {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}${props.wsUrl}`;
}

function connect() {
  if (!window.WebSocket) {
    status.value = "closed";
    return;
  }
  status.value = "connecting";
  socket = new WebSocket(endpoint());

  socket.onopen = () => {
    attempts = 0;
    status.value = "open";
  };

  socket.onmessage = (message) => {
    let data;
    try {
      data = JSON.parse(message.data);
    } catch (error) {
      return;
    }
    if (data.type !== "event" || !data.event) return;
    const event = data.event;
    events.value = [event, ...events.value].slice(0, 50);
    applyMetrics(event);
  };

  socket.onclose = () => {
    status.value = "closed";
    attempts += 1;
    const delay = Math.min(1000 * 2 ** (attempts - 1), 15000);
    retry = window.setTimeout(connect, delay);
  };
}

function applyMetrics(event) {
  const kind = event.kind;
  if (kind === "entry_created" || kind === "entry_updated") {
    metrics.value = {
      ...metrics.value,
      entries: (metrics.value.entries || 0) + (kind === "entry_created" ? 1 : 0),
    };
    bumpToday();
  } else if (kind === "session_ended") {
    const minutes = (event.payload || {}).minutes || 0;
    metrics.value = { ...metrics.value, minutes: (metrics.value.minutes || 0) + minutes };
  } else if (kind === "todo_toggled") {
    const done = (event.payload || {}).done;
    metrics.value = {
      ...metrics.value,
      todos: Math.max(0, (metrics.value.todos || 0) + (done ? -1 : 1)),
    };
  }
}

function bumpToday() {
  const rows = series.value.slice();
  if (!rows.length) return;
  const last = rows[rows.length - 1];
  rows[rows.length - 1] = { ...last, count: Number(last.count || 0) + 1 };
  series.value = rows;
}

onMounted(connect);
onBeforeUnmount(() => {
  if (retry) window.clearTimeout(retry);
  if (socket) socket.close();
});
</script>

<template>
  <div class="live">
    <div class="live__bar" :class="'live__bar--' + status">
      <span class="live__dot"></span>
      <span>{{ statusText }}</span>
    </div>

    <MetricCards :metrics="metrics" />

    <div class="live__grid">
      <TrendChart :series="series" />
      <EventStream :events="events" :active-kind="activeKind" @select-kind="activeKind = $event" />
    </div>
  </div>
</template>

<style scoped>
.live {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.live__bar {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  align-self: flex-start;
  padding: 0.2rem 0.6rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  font-size: 0.78rem;
  color: var(--muted);
}

.live__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--muted);
}

.live__bar--open .live__dot {
  background: #10b981;
}

.live__bar--connecting .live__dot {
  background: #f59e0b;
}

.live__bar--closed .live__dot {
  background: #ef4444;
}

.live__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  gap: 1.25rem;
  align-items: start;
}

@media (max-width: 900px) {
  .live__grid {
    grid-template-columns: 1fr;
  }
}
</style>
