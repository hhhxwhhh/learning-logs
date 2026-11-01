<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import MetricCards from "./components/MetricCards.vue";
import EventStream from "./components/EventStream.vue";

const props = defineProps({
  initial: { type: Object, default: () => ({}) },
  wsUrl: { type: String, default: "/ws/live/" },
});

const status = ref("connecting");
const events = ref(props.initial.events || []);
const metrics = ref({ ...(props.initial.metrics || {}) });
let socket = null;
let retry = null;
let attempts = 0;

const statusText = computed(() => {
  if (status.value === "open") return "已连接";
  if (status.value === "closed") return "已断开";
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
    const delay = Math.min(1000 * attempts, 15000);
    retry = window.setTimeout(connect, delay);
  };
}

function applyMetrics(event) {
  const kind = event.kind;
  if (kind === "entry_created" || kind === "entry_updated") {
    metrics.value = { ...metrics.value, entries: (metrics.value.entries || 0) + (kind === "entry_created" ? 1 : 0) };
  } else if (kind === "session_ended") {
    const minutes = (event.payload || {}).minutes || 0;
    metrics.value = { ...metrics.value, minutes: (metrics.value.minutes || 0) + minutes };
  } else if (kind === "todo_toggled") {
    const done = (event.payload || {}).done;
    if (done) {
      metrics.value = { ...metrics.value, todos: Math.max(0, (metrics.value.todos || 0) - 1) };
    } else {
      metrics.value = { ...metrics.value, todos: (metrics.value.todos || 0) + 1 };
    }
  }
}

onMounted(connect);
onBeforeUnmount(() => {
  if (retry) window.clearTimeout(retry);
  if (socket) socket.close();
});
</script>

<template>
  <div class="live">
    <MetricCards :metrics="metrics" />
    <EventStream :events="events" />
  </div>
</template>

<style scoped>
.live {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}
</style>
