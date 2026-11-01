<script setup>
import { RouterLink, RouterView } from "vue-router";
import { useLiveSocket } from "./composables/useLiveSocket";
import { useLiveStore } from "./stores/live";

const props = defineProps({
  initial: { type: Object, default: () => ({}) },
  wsUrl: { type: String, default: "/ws/live/" },
});

const store = useLiveStore();
// 首屏数据同步灌进去，路由视图首次渲染时就能拿到内容
store.hydrate(props.initial);

useLiveSocket(props.wsUrl);

const tabs = [
  { name: "overview", label: "概览" },
  { name: "events", label: "事件流" },
  { name: "trends", label: "趋势" },
];
</script>

<template>
  <div class="live">
    <div class="live__head">
      <nav class="live__tabs">
        <RouterLink
          v-for="tab in tabs"
          :key="tab.name"
          class="live__tab"
          :to="{ name: tab.name }"
        >
          {{ tab.label }}
        </RouterLink>
      </nav>
      <span class="live__bar" :class="'live__bar--' + store.status">
        <span class="live__dot"></span>
        <span>{{ store.statusText }}</span>
      </span>
    </div>

    <RouterView />
  </div>
</template>

<style scoped>
.live {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.live__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.live__tabs {
  display: flex;
  gap: 0.25rem;
  padding: 0.2rem;
  border: 1px solid var(--line);
  border-radius: 999px;
}

.live__tab {
  padding: 0.25rem 0.85rem;
  border-radius: 999px;
  font-size: 0.85rem;
  color: var(--muted);
  text-decoration: none;
}

.live__tab.router-link-active {
  background: var(--accent, #2563eb);
  color: #fff;
}

.live__bar {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
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
</style>
