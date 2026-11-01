<script setup>
import { ref } from "vue";
import MetricCards from "../components/MetricCards.vue";
import TrendChart from "../components/TrendChart.vue";
import EventStream from "../components/EventStream.vue";
import { useLiveStore } from "../stores/live";

const store = useLiveStore();
const activeKind = ref("all");
</script>

<template>
  <div class="overview">
    <MetricCards :metrics="store.metrics" />
    <div class="overview__grid">
      <TrendChart :series="store.series" />
      <EventStream
        :events="store.events"
        :active-kind="activeKind"
        @select-kind="activeKind = $event"
      />
    </div>
  </div>
</template>

<style scoped>
.overview {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.overview__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  gap: 1.25rem;
  align-items: start;
}

@media (max-width: 900px) {
  .overview__grid {
    grid-template-columns: 1fr;
  }
}
</style>
