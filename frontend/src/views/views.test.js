import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import OverviewView from "./OverviewView.vue";
import EventsView from "./EventsView.vue";
import TrendsView from "./TrendsView.vue";
import { useLiveStore } from "../stores/live";

describe("OverviewView", () => {
  it("渲染指标卡与事件流", () => {
    const pinia = createPinia();
    const store = useLiveStore(pinia);
    store.hydrate({
      metrics: { entries: 3, minutes: 20, cards: 1, todos: 0 },
      events: [],
      series: [],
    });
    const wrapper = mount(OverviewView, { global: { plugins: [pinia] } });
    expect(wrapper.findAll(".metric__label").length).toBe(4);
    expect(wrapper.text()).toContain("实时事件");
  });
});

describe("EventsView", () => {
  it("展示事件数量", () => {
    const pinia = createPinia();
    const store = useLiveStore(pinia);
    store.hydrate({
      events: [
        { event_id: "e1", kind: "entry_created", summary: "写了一条", created_at: "2026-11-01T10:00:00Z" },
      ],
    });
    const wrapper = mount(EventsView, { global: { plugins: [pinia] } });
    expect(wrapper.text()).toContain("写了一条");
    expect(wrapper.text()).toContain("1 / 1 条");
  });
});

describe("TrendsView", () => {
  it("统计近七日合计与日均", () => {
    const pinia = createPinia();
    const store = useLiveStore(pinia);
    store.hydrate({
      series: [
        { date: "2026-11-01", count: 2 },
        { date: "2026-11-02", count: 4 },
      ],
    });
    const wrapper = mount(TrendsView, { global: { plugins: [pinia] } });
    expect(wrapper.text()).toContain("6");
    expect(wrapper.text()).toContain("3.0");
  });
});
