<script setup>
import { computed } from "vue";

const props = defineProps({
  series: { type: Array, default: () => [] },
});

const MAX_BAR = 96;

const bars = computed(() => {
  const rows = props.series || [];
  if (!rows.length) return [];
  const peak = Math.max(...rows.map((row) => Number(row.count || 0)), 1);
  return rows.map((row) => ({
    ...row,
    height: Math.max(4, Math.round((Number(row.count || 0) / peak) * MAX_BAR)),
  }));
});

function label(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}
</script>

<template>
  <section class="card">
    <div class="card__head">
      <h3>近 7 天笔记</h3>
      <span class="tiny muted">共 {{ series.reduce((sum, row) => sum + Number(row.count || 0), 0) }} 条</span>
    </div>
    <div class="card__body">
      <div v-if="bars.length" class="chart">
        <div v-for="bar in bars" :key="bar.date" class="chart__col">
          <span class="chart__value">{{ bar.count }}</span>
          <div class="chart__track">
            <div class="chart__bar" :style="{ height: bar.height + 'px' }"></div>
          </div>
          <span class="chart__label">{{ label(bar.date) }}</span>
        </div>
      </div>
      <p v-else class="muted small">还没有数据。</p>
    </div>
  </section>
</template>

<style scoped>
.chart {
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  height: 140px;
}

.chart__col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.3rem;
  height: 100%;
  justify-content: flex-end;
}

.chart__value {
  font-size: 0.72rem;
  color: var(--muted);
}

.chart__track {
  flex: 1;
  width: 100%;
  display: flex;
  align-items: flex-end;
}

.chart__bar {
  width: 100%;
  border-radius: 4px 4px 0 0;
  background: linear-gradient(180deg, var(--accent), color-mix(in srgb, var(--accent) 45%, transparent));
  transition: height 0.3s ease;
}

.chart__label {
  font-size: 0.7rem;
  color: var(--muted);
  white-space: nowrap;
}
</style>
