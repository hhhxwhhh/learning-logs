import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 构建产物直接输出到 Django 的 static/live，由 WhiteNoise 或 collectstatic 托管。
export default defineConfig({
  plugins: [vue()],
  base: "/static/live/",
  build: {
    outDir: "../static/live",
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        entryFileNames: "app.js",
        chunkFileNames: "chunk-[name].js",
        assetFileNames: "app.[ext]",
      },
    },
  },
});
