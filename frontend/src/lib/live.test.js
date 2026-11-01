import { describe, expect, it } from "vitest";
import {
  applyMetrics,
  barHeights,
  bucketOf,
  clockTime,
  countByBucket,
  durationText,
  filterEvents,
  prependEvent,
  relativeTime,
} from "./live";

describe("bucketOf", () => {
  it("按事件类型前缀归类", () => {
    expect(bucketOf("entry_created")).toBe("entry");
    expect(bucketOf("session_ended")).toBe("session");
    expect(bucketOf("card_reviewed")).toBe("card");
    expect(bucketOf("todo_toggled")).toBe("todo");
    expect(bucketOf("topic_created")).toBe("topic");
  });

  it("未知类型归到 other", () => {
    expect(bucketOf("something_else")).toBe("other");
    expect(bucketOf("")).toBe("other");
    expect(bucketOf(undefined)).toBe("other");
  });
});

describe("applyMetrics", () => {
  it("新建笔记时条目数加一", () => {
    const result = applyMetrics({ entries: 2 }, { kind: "entry_created" });
    expect(result.entries).toBe(3);
  });

  it("修改笔记不改变条目数", () => {
    const result = applyMetrics({ entries: 2 }, { kind: "entry_updated" });
    expect(result.entries).toBe(2);
  });

  it("结束专注时累加时长", () => {
    const result = applyMetrics({ minutes: 10 }, { kind: "session_ended", payload: { minutes: 25 } });
    expect(result.minutes).toBe(35);
  });

  it("勾选待办时数量减一", () => {
    const result = applyMetrics({ todos: 3 }, { kind: "todo_toggled", payload: { done: true } });
    expect(result.todos).toBe(2);
  });

  it("取消勾选时数量加一", () => {
    const result = applyMetrics({ todos: 3 }, { kind: "todo_toggled", payload: { done: false } });
    expect(result.todos).toBe(4);
  });

  it("待办数不会变成负数", () => {
    const result = applyMetrics({ todos: 0 }, { kind: "todo_toggled", payload: { done: true } });
    expect(result.todos).toBe(0);
  });

  it("不修改传入的对象", () => {
    const original = { entries: 1 };
    applyMetrics(original, { kind: "entry_created" });
    expect(original.entries).toBe(1);
  });
});

describe("countByBucket", () => {
  it("按类型统计数量", () => {
    const counts = countByBucket([
      { kind: "entry_created" },
      { kind: "entry_created" },
      { kind: "card_reviewed" },
    ]);
    expect(counts.entry).toBe(2);
    expect(counts.card).toBe(1);
  });

  it("空列表返回空对象", () => {
    expect(countByBucket([])).toEqual({});
    expect(countByBucket(undefined)).toEqual({});
  });
});

describe("filterEvents", () => {
  const events = [
    { event_id: "1", kind: "entry_created" },
    { event_id: "2", kind: "session_ended" },
    { event_id: "3", kind: "entry_updated" },
  ];

  it("全部筛选时返回原列表", () => {
    expect(filterEvents(events, "all")).toHaveLength(3);
  });

  it("按类型筛选", () => {
    const filtered = filterEvents(events, "entry");
    expect(filtered).toHaveLength(2);
    expect(filtered[0].event_id).toBe("1");
  });

  it("没有匹配时返回空数组", () => {
    expect(filterEvents(events, "card")).toHaveLength(0);
  });
});

describe("prependEvent", () => {
  it("新事件排在最前", () => {
    const result = prependEvent([{ event_id: "1" }], { event_id: "2" });
    expect(result[0].event_id).toBe("2");
  });

  it("超出上限时截断", () => {
    const events = Array.from({ length: 5 }, (_, index) => ({ event_id: String(index) }));
    const result = prependEvent(events, { event_id: "new" }, 3);
    expect(result).toHaveLength(3);
    expect(result[0].event_id).toBe("new");
  });
});

describe("relativeTime", () => {
  const now = new Date("2026-11-01T12:00:00Z").getTime();

  it("几秒内显示刚刚", () => {
    expect(relativeTime("2026-11-01T11:59:58Z", now)).toBe("刚刚");
  });

  it("显示秒数", () => {
    expect(relativeTime("2026-11-01T11:59:30Z", now)).toBe("30 秒前");
  });

  it("显示分钟数", () => {
    expect(relativeTime("2026-11-01T11:45:00Z", now)).toBe("15 分钟前");
  });

  it("显示小时数", () => {
    expect(relativeTime("2026-11-01T09:00:00Z", now)).toBe("3 小时前");
  });

  it("超过一天显示日期", () => {
    expect(relativeTime("2026-10-30T12:00:00Z", now)).toContain("2026");
  });

  it("空值与非法值返回空串", () => {
    expect(relativeTime("", now)).toBe("");
    expect(relativeTime("不是时间", now)).toBe("");
  });
});

describe("clockTime", () => {
  it("非法时间返回空串", () => {
    expect(clockTime("不是时间")).toBe("");
    expect(clockTime(null)).toBe("");
  });

  it("合法时间返回时分秒", () => {
    expect(clockTime("2026-11-01T12:34:56Z")).toMatch(/\d{2}:\d{2}:\d{2}/);
  });
});

describe("durationText", () => {
  it("只有分钟", () => {
    expect(durationText(25)).toBe("25 分钟");
  });

  it("整小时", () => {
    expect(durationText(120)).toBe("2 小时");
  });

  it("小时与分钟混合", () => {
    expect(durationText(95)).toBe("1 小时 35 分");
  });

  it("空值当作 0", () => {
    expect(durationText(undefined)).toBe("0 分钟");
  });
});

describe("barHeights", () => {
  it("按峰值缩放", () => {
    const bars = barHeights([{ count: 0 }, { count: 10 }, { count: 5 }]);
    expect(bars[1].height).toBe(96);
    expect(bars[2].height).toBe(48);
  });

  it("空柱子也有最小高度", () => {
    const bars = barHeights([{ count: 0 }, { count: 10 }]);
    expect(bars[0].height).toBe(4);
  });

  it("空数组返回空", () => {
    expect(barHeights([])).toEqual([]);
  });
});
