import { createApp } from "vue";
import App from "./App.vue";

const mount = document.getElementById("live-app");
if (mount) {
  const raw = document.getElementById("live-initial")?.textContent || "{}";
  let initial = {};
  try {
    initial = JSON.parse(raw);
  } catch (error) {
    console.warn("首屏数据解析失败", error);
  }
  createApp(App, { initial, wsUrl: mount.dataset.wsUrl || "/ws/live/" }).mount(mount);
}
