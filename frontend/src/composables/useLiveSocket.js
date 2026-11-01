/**
 * WebSocket 连接管理。
 *
 * 断线后按指数退避重连，连接状态写回 store，视图只负责显示。
 */

import { onBeforeUnmount, onMounted } from "vue";
import { useLiveStore } from "../stores/live";

const MAX_DELAY = 15000;

export function useLiveSocket(wsUrl) {
  const store = useLiveStore();
  let socket = null;
  let retry = null;
  let attempts = 0;

  function endpoint() {
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    return `${scheme}://${window.location.host}${wsUrl}`;
  }

  function schedule() {
    attempts += 1;
    const delay = Math.min(1000 * 2 ** (attempts - 1), MAX_DELAY);
    retry = window.setTimeout(connect, delay);
  }

  function connect() {
    if (!window.WebSocket) {
      store.status = "closed";
      return;
    }
    store.status = "connecting";
    socket = new WebSocket(endpoint());

    socket.onopen = () => {
      attempts = 0;
      store.status = "open";
    };

    socket.onmessage = (message) => {
      let data;
      try {
        data = JSON.parse(message.data);
      } catch (error) {
        return;
      }
      if (data.type !== "event" || !data.event) return;
      store.apply(data.event);
    };

    socket.onclose = () => {
      store.status = "closed";
      schedule();
    };
  }

  onMounted(connect);

  onBeforeUnmount(() => {
    if (retry) window.clearTimeout(retry);
    if (socket) {
      socket.onclose = null;
      socket.close();
    }
  });

  return { store };
}
