import { createRouter, createWebHashHistory } from "vue-router";
import OverviewView from "./views/OverviewView.vue";
import EventsView from "./views/EventsView.vue";
import TrendsView from "./views/TrendsView.vue";

export const routes = [
  { path: "/", name: "overview", component: OverviewView, meta: { title: "概览" } },
  { path: "/events", name: "events", component: EventsView, meta: { title: "事件流" } },
  { path: "/trends", name: "trends", component: TrendsView, meta: { title: "趋势" } },
];

export function createLiveRouter() {
  return createRouter({
    // 用 hash 模式，前端只挂在 /live/ 一个地址上，服务端不用额外配子路由。
    history: createWebHashHistory(),
    routes,
  });
}
