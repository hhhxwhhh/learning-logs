import { beforeEach, describe, expect, it } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia } from "pinia";
import App from "./App.vue";
import { createLiveRouter } from "./router";

async function mountApp(initial = {}) {
  const pinia = createPinia();
  const router = createLiveRouter();
  const wrapper = mount(App, {
    props: { initial, wsUrl: "/ws/live/" },
    global: { plugins: [pinia, router] },
  });
  // RouterView 里的组件是异步解析的，等一拍才能拿到渲染结果
  await flushPromises();
  return { wrapper, router };
}

describe("看板应用", () => {
  // hash 模式的路由会写进地址栏，测试之间要清掉，否则会互相影响
  beforeEach(() => {
    window.location.hash = "";
  });

  it("挂载后渲染出概览视图", async () => {
    const { wrapper } = await mountApp({
      metrics: { entries: 2, minutes: 30, cards: 1, todos: 0 },
      events: [],
      series: [],
    });
    expect(wrapper.find(".live").exists()).toBe(true);
    expect(wrapper.text()).toContain("概览");
    expect(wrapper.findAll(".metric__label").length).toBe(4);
  });

  it("导航里有三个视图", async () => {
    const { wrapper } = await mountApp({});
    const tabs = wrapper.findAll(".live__tab").map((node) => node.text());
    expect(tabs).toEqual(["概览", "事件流", "趋势"]);
  });

  it("切到事件流路由后展示事件", async () => {
    const { wrapper, router } = await mountApp({
      events: [
        {
          event_id: "e1",
          kind: "entry_created",
          summary: "写了一条笔记",
          created_at: "2026-11-01T10:00:00Z",
        },
      ],
    });
    await router.push("/events");
    await flushPromises();
    expect(wrapper.text()).toContain("写了一条笔记");
  });

  it("切到趋势路由后展示统计", async () => {
    const { wrapper, router } = await mountApp({
      series: [
        { date: "2026-11-01", count: 2 },
        { date: "2026-11-02", count: 4 },
      ],
    });
    await router.push("/trends");
    await flushPromises();
    expect(wrapper.text()).toContain("近七日合计");
    expect(wrapper.findAll(".chart__col").length).toBe(2);
  });

  it("首屏事件灌进 store 并显示", async () => {
    const { wrapper } = await mountApp({
      events: [
        {
          event_id: "e2",
          kind: "entry_created",
          summary: "首屏的事件",
          created_at: "2026-11-01T10:00:00Z",
        },
      ],
    });
    expect(wrapper.text()).toContain("首屏的事件");
  });
});
