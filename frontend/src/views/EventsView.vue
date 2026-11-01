<script setup>
import { ref } from "vue";
import EventStream from "../components/EventStream.vue";
import { useLiveStore } from "../stores/live";

const store = useLiveStore();
const activeKind = ref("all");
</script>

<template>
  <div class="events">
    <EventStream
      :events="store.events"
      :active-kind="activeKind"
      @select-kind="activeKind = $event"
    />
  </div>
</template>

<style scoped>
.events {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
</style>
