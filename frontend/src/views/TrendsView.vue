<script setup>
import { computed } from "vue";
import TrendChart from "../components/TrendChart.vue";
import { useLiveStore } from "../stores/live";

const store = useLiveStore();

const summary = computed(() => {
  const counts = store.series.map((item) => Number(item.count || 0));
  const total = counts.reduce((sum, value) => sum + value, 0);
  const best = counts.length ? Math.max(...counts) : 0;
  const average = counts.length ? total / counts.length : 0;
  return { total, best, average: average.toFixed(1) };
});
</script>

<template>
  <div class="trends">
    <TrendChart :series="store.series" />

    <dl class="trends__stats">
      <div class="trends__stat">
        <dt>近七日合计</dt>
        <dd>{{ summary.total }}</dd>
      </div>
      <div class="trends__stat">
        <dt>单日最高</dt>
        <dd>{{ summary.best }}</dd>
      </div>
      <div class="trends__stat">
        <dt>日均</dt>
        <dd>{{ summary.average }}</dd>
      </div>
    </dl>
  </div>
</template>

<style scoped>
.trends {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.trends__stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
  margin: 0;
}

.trends__stat {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.9rem 1rem;
  background: var(--surface, transparent);
}

.trends__stat dt {
  font-size: 0.78rem;
  color: var(--muted);
}

.trends__stat dd {
  margin: 0.3rem 0 0;
  font-size: 1.5rem;
  font-variant-numeric: tabular-nums;
}

@media (max-width: 640px) {
  .trends__stats {
    grid-template-columns: 1fr;
  }
}
</style>
