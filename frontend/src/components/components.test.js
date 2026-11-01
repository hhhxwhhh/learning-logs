import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import MetricCards from "./MetricCards.vue";
import TrendChart from "./TrendChart.vue";
import EventStream from "./EventStream.vue";

describe("MetricCards", () => {
  it("展示四个指标", () => {
    const wrapper = mount(MetricCards, {
      props: { metrics: { entries: 3, minutes: 65, cards: 2, todos: 1 } },
    });
    const labels = wrapper.findAll(".metric__label").map((node) => node.text());
    expect(labels).toEqual(["今日笔记", "专注时长", "待复习", "待办"]);
  });

  it("时长换算成中文", () => {
    const wrapper = mount(MetricCards, { props: { metrics: { minutes: 95 } } });
    expect(wrapper.text()).toContain("1 小时 35 分");
  });

  it("缺省数据显示 0", () => {
    const wrapper = mount(MetricCards, { props: { metrics: {} } });
    expect(wrapper.text()).toContain("0");
  });
});

describe("TrendChart", () => {
  const series = [
    { date: "2026-11-01", count: 1 },
    { date: "2026-11-02", count: 3 },
  ];

  it("按数据渲染柱子", () => {
    const wrapper = mount(TrendChart, { props: { series } });
    expect(wrapper.findAll(".chart__col")).toHaveLength(2);
  });

  it("显示总数", () => {
    const wrapper = mount(TrendChart, { props: { series } });
    expect(wrapper.text()).toContain("共 4 条");
  });

  it("没有数据时显示提示", () => {
    const wrapper = mount(TrendChart, { props: { series: [] } });
    expect(wrapper.text()).toContain("还没有数据");
  });
});

describe("EventStream", () => {
  const events = [
    {
      event_id: "1",
      kind: "entry_created",
      label: "新建笔记",
      summary: "写了一条笔记",
      created_at: "2026-11-01T12:00:00Z",
    },
    {
      event_id: "2",
      kind: "card_reviewed",
      label: "复习闪卡",
      summary: "复习了一张卡",
      created_at: "2026-11-01T12:01:00Z",
    },
  ];

  it("渲染事件列表", () => {
    const wrapper = mount(EventStream, { props: { events } });
    expect(wrapper.findAll(".list__item")).toHaveLength(2);
    expect(wrapper.text()).toContain("写了一条笔记");
  });

  it("按类型筛选后只显示匹配的", () => {
    const wrapper = mount(EventStream, { props: { events, activeKind: "entry" } });
    expect(wrapper.findAll(".list__item")).toHaveLength(1);
  });

  it("点击筛选按钮发出事件", () => {
    const wrapper = mount(EventStream, { props: { events } });
    const chips = wrapper.findAll(".chip");
    chips[1].trigger("click");
    expect(wrapper.emitted("select-kind")[0]).toEqual(["entry"]);
  });

  it("没有事件时给出提示", () => {
    const wrapper = mount(EventStream, { props: { events: [] } });
    expect(wrapper.text()).toContain("还没有事件");
  });
});
