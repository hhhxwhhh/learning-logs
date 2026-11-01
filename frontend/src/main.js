import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { createLiveRouter } from "./router";

const mount = document.getElementById("live-app");
if (mount) {
  const raw = document.getElementById("live-initial")?.textContent || "{}";
  let initial = {};
  try {
    initial = JSON.parse(raw);
  } catch (error) {
    console.warn("首屏数据解析失败", error);
  }

  const app = createApp(App, { initial, wsUrl: mount.dataset.wsUrl || "/ws/live/" });
  app.use(createPinia());
  app.use(createLiveRouter());
  app.mount(mount);
}
