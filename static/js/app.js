/* 知迹 Learning Log · 交互脚本（原生 JS，无框架依赖） */
(function () {
  "use strict";

  const THEME_KEY = "ll-theme";
  const root = document.documentElement;

  /* ---------------------------------------------------------------- 主题 */
  function applyTheme(theme) {
    if (theme === "dark" || theme === "light") {
      root.setAttribute("data-theme", theme);
    } else {
      root.removeAttribute("data-theme");
    }
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute("content", theme === "dark" ? "#0b0c10" : "#f6f6f3");
    }
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    });
  }

  function currentTheme() {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored) return stored;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  // 首屏尽早应用，避免闪白
  applyTheme(localStorage.getItem(THEME_KEY) || currentTheme());

  window.toggleTheme = function () {
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
  };

  /* ------------------------------------------------------------ 移动端导航 */
  function initNavToggle() {
    const toggle = document.querySelector("[data-nav-toggle]");
    const panel = document.querySelector("[data-mobile-nav]");
    if (!toggle || !panel) return;
    toggle.addEventListener("click", function () {
      const open = panel.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  /* --------------------------------------------------------------- 下拉菜单 */
  function initDropdowns() {
    document.addEventListener("click", function (event) {
      document.querySelectorAll("details.dropmenu[open]").forEach(function (menu) {
        if (!menu.contains(event.target)) menu.removeAttribute("open");
      });
    });
  }

  /* ------------------------------------------------------------------ 提示 */
  function initToasts() {
    document.querySelectorAll("[data-toast]").forEach(function (toast) {
      const close = toast.querySelector("[data-toast-close]");
      if (close) {
        close.addEventListener("click", function () {
          toast.remove();
        });
      }
      // 错误提示停留更久，方便阅读
      const delay = toast.classList.contains("toast--error") ? 7000 : 4200;
      setTimeout(function () {
        toast.style.transition = "opacity 320ms ease, transform 320ms ease";
        toast.style.opacity = "0";
        toast.style.transform = "translateY(-6px)";
        setTimeout(function () {
          toast.remove();
        }, 340);
      }, delay);
    });
  }

  /* ------------------------------------------------------- 危险操作二次确认 */
  function initConfirm() {
    document.addEventListener("submit", function (event) {
      const form = event.target;
      if (!(form instanceof HTMLFormElement)) return;
      const message = form.getAttribute("data-confirm");
      if (message && !window.confirm(message)) {
        event.preventDefault();
      }
    });
  }

  /* ------------------------------------------------------------ 代码块复制 */
  function enhanceCodeBlocks(scope) {
    (scope || document).querySelectorAll(".prose pre").forEach(function (pre) {
      if (pre.querySelector(".copy-code")) return;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "copy-code";
      btn.textContent = "复制";
      btn.addEventListener("click", function () {
        const code = pre.querySelector("code");
        const text = code ? code.innerText : pre.innerText;
        if (navigator.clipboard) {
          navigator.clipboard.writeText(text).then(function () {
            btn.textContent = "已复制";
            setTimeout(function () {
              btn.textContent = "复制";
            }, 1500);
          });
        }
      });
      pre.appendChild(btn);
    });
  }

  /* ------------------------------------------------------------- 自动增高 */
  function initAutoGrow() {
    document.querySelectorAll("textarea[data-autogrow]").forEach(function (el) {
      const resize = function () {
        el.style.height = "auto";
        el.style.height = Math.min(el.scrollHeight, 220) + "px";
      };
      el.addEventListener("input", resize);
      resize();
    });
  }

  /* ---------------------------------------------------------------- 工具函数 */
  window.LL = {
    csrfToken: function () {
      const match = document.cookie.match(/(^|;\s*)csrftoken=([^;]+)/);
      return match ? decodeURIComponent(match[2]) : "";
    },
    toast: function (message, type) {
      let stack = document.querySelector(".toast-stack");
      if (!stack) {
        stack = document.createElement("div");
        stack.className = "toast-stack";
        document.body.appendChild(stack);
      }
      const el = document.createElement("div");
      el.className = "toast toast--" + (type || "info");
      el.setAttribute("data-toast", "");
      el.innerHTML =
        '<div style="flex:1">' +
        String(message).replace(/[<>&]/g, function (c) {
          return { "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c];
        }) +
        "</div>" +
        '<button type="button" class="toast__close" data-toast-close aria-label="关闭">✕</button>';
      stack.appendChild(el);
      initToasts();
    },
    enhanceCodeBlocks: enhanceCodeBlocks,
  };

  document.addEventListener("DOMContentLoaded", function () {
    initNavToggle();
    initDropdowns();
    initToasts();
    initConfirm();
    initAutoGrow();
    enhanceCodeBlocks();
  });
})();
