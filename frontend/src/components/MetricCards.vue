<script setup>
defineProps({
  metrics: { type: Object, default: () => ({}) },
});

function duration(minutes) {
  const value = Number(minutes || 0);
  const hours = Math.floor(value / 60);
  const rest = value % 60;
  if (hours && rest) return `${hours} 小时 ${rest} 分`;
  if (hours) return `${hours} 小时`;
  return `${rest} 分钟`;
}
</script>

<template>
  <div class="grid metrics">
    <div class="metric">
      <span class="metric__label">今日笔记</span>
      <span class="metric__value">{{ metrics.entries || 0 }}</span>
      <span class="metric__hint">今天写了多少条</span>
    </div>
    <div class="metric">
      <span class="metric__label">专注时长</span>
      <span class="metric__value" style="font-size: 1.3rem">{{ duration(metrics.minutes) }}</span>
      <span class="metric__hint">番茄钟与计时</span>
    </div>
    <div class="metric">
      <span class="metric__label">待复习</span>
      <span class="metric__value">{{ metrics.cards || 0 }}</span>
      <span class="metric__hint">到期闪卡</span>
    </div>
    <div class="metric">
      <span class="metric__label">待办</span>
      <span class="metric__value">{{ metrics.todos || 0 }}</span>
      <span class="metric__hint">未完成的条目</span>
    </div>
  </div>
</template>
