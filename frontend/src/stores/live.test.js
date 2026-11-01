import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useLiveStore } from "./live";

describe("live store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("首屏数据灌进状态", () => {
    const store = useLiveStore();
    store.hydrate({
      events: [{ event_id: "e1", kind: "entry_created" }],
      metrics: { entries: 2 },
      series: [{ date: "2026-11-01", count: 2 }],
    });
    expect(store.events).toHaveLength(1);
    expect(store.metrics.entries).toBe(2);
    expect(store.series).toHaveLength(1);
  });

  it("空首屏数据不会报错", () => {
    const store = useLiveStore();
    store.hydrate({});
    expect(store.events).toEqual([]);
    expect(store.metrics).toEqual({});
  });

  it("收到事件后追加到流里并更新指标", () => {
    const store = useLiveStore();
    store.hydrate({ metrics: { entries: 1 } });
    store.apply({
      event_id: "e1",
      kind: "entry_created",
      summary: "写了一条",
      created_at: "2026-11-01T10:00:00Z",
    });
    expect(store.events).toHaveLength(1);
    expect(store.events[0].kind).toBe("entry_created");
    expect(store.metrics.entries).toBe(2);
  });

  it("写笔记时趋势图最后一天加一", () => {
    const store = useLiveStore();
    store.hydrate({ series: [{ date: "2026-11-01", count: 1 }, { date: "2026-11-02", count: 0 }] });
    store.apply({ event_id: "e2", kind: "entry_created" });
    expect(store.series[1].count).toBe(1);
    expect(store.series[0].count).toBe(1);
  });

  it("非笔记事件不影响趋势图", () => {
    const store = useLiveStore();
    store.hydrate({ series: [{ date: "2026-11-01", count: 3 }] });
    store.apply({ event_id: "e3", kind: "session_ended" });
    expect(store.series[0].count).toBe(3);
  });

  it("连接状态有对应文案", () => {
    const store = useLiveStore();
    store.status = "open";
    expect(store.statusText).toBe("已连接");
    store.status = "closed";
    expect(store.statusText).toContain("重连");
    store.status = "connecting";
    expect(store.statusText).toBe("连接中");
  });
});
