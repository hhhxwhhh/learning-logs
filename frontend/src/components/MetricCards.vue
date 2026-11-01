<script setup>
import { durationText } from "../lib/live";

defineProps({
  metrics: { type: Object, default: () => ({}) },
});
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
      <span class="metric__value" style="font-size: 1.3rem">{{ durationText(metrics.minutes) }}</span>
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
