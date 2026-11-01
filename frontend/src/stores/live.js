/**
 * 实时看板的状态仓库。
 *
 * 连接、事件流、指标都放在这里，视图组件只读状态，不各自维护一份。
 */

import { defineStore } from "pinia";
import { applyMetrics, prependEvent } from "../lib/live";

export const useLiveStore = defineStore("live", {
  state: () => ({
    status: "connecting",
    events: [],
    metrics: {},
    series: [],
    attempts: 0,
  }),

  getters: {
    statusText(state) {
      if (state.status === "open") return "已连接";
      if (state.status === "closed") return "连接断开，正在重连";
      return "连接中";
    },
    dueToday(state) {
      return Number(state.metrics.cards || 0);
    },
  },

  actions: {
    hydrate(initial) {
      this.events = initial.events || [];
      this.metrics = { ...(initial.metrics || {}) };
      this.series = initial.series || [];
    },

    /** 收到一条事件：追加到流里并同步指标。 */
    apply(event) {
      this.events = prependEvent(this.events, event);
      this.metrics = applyMetrics(this.metrics, event);
      if (event.kind === "entry_created") {
        this.bumpToday();
      }
    },

    /** 趋势图的最后一天加一，用于写完笔记后即时反馈。 */
    bumpToday() {
      const rows = this.series.slice();
      if (!rows.length) return;
      const last = rows[rows.length - 1];
      rows[rows.length - 1] = { ...last, count: Number(last.count || 0) + 1 };
      this.series = rows;
    },
  },
});
