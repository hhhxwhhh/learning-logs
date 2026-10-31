/* 待办清单：勾选后异步写回笔记，页面局部更新。 */
(function () {
  "use strict";

  function updateCounter(open) {
    const counter = document.getElementById("todo-open");
    if (counter && typeof open === "number") {
      counter.textContent = String(open);
    }
  }

  document.addEventListener("click", function (event) {
    const button = event.target.closest("[data-toggle-todo]");
    if (!button) {
      return;
    }
    event.preventDefault();
    if (button.disabled) {
      return;
    }
    button.disabled = true;

    const row = button.closest(".todo");
    const body = new URLSearchParams({ index: button.dataset.index || "0" });

    fetch(button.dataset.url, {
      method: "POST",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": window.LL.csrfToken(),
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: body.toString(),
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.data.ok) {
          window.LL.toast(result.data.error || "更新失败，请刷新后重试。", "error");
          return;
        }
        const done = result.data.done;
        button.setAttribute("aria-pressed", done ? "true" : "false");
        button.setAttribute(
          "aria-label",
          (done ? "取消完成" : "标记完成") + "：" + (row ? row.textContent.trim() : "")
        );
        if (row) {
          row.classList.toggle("todo--done", done);
        }
        updateCounter(result.data.open);
        window.LL.toast(done ? "已完成" : "已恢复为待办", "success");
      })
      .catch(function () {
        window.LL.toast("网络异常，待办没有更新。", "error");
      })
      .finally(function () {
        button.disabled = false;
      });
  });
})();
