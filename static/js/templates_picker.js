/* 笔记写作模板：点击后把骨架填入编辑器。 */
(function () {
  var TEMPLATES = {
    daily: [
      "## 今天学了什么",
      "- 关键概念：",
      "- 代码示例：",
      "",
      "## 卡住的地方",
      "- ",
      "",
      "## 下一步",
      "- ",
    ].join("\n"),
    concept: [
      "## 概念",
      "一句话定义：",
      "",
      "## 为什么需要它",
      "- 解决的问题：",
      "- 不用的话会怎样：",
      "",
      "## 例子",
      "```",
      "",
      "```",
      "",
      "## 容易混淆的点",
      "- ",
    ].join("\n"),
    bug: [
      "## 现象",
      "报错信息 / 表现：",
      "",
      "## 原因",
      "- 根因：",
      "- 为什么一开始没发现：",
      "",
      "## 解决办法",
      "```",
      "",
      "```",
      "",
      "## 下次怎么避免",
      "- [ ] ",
    ].join("\n"),
    plan: [
      "## 目标",
      "想在什么时候做到什么程度：",
      "",
      "## 拆解",
      "- [ ] 第一步：",
      "- [ ] 第二步：",
      "- [ ] 第三步：",
      "",
      "## 需要的资源",
      "- ",
    ].join("\n"),
  };

  var picker = document.querySelector("[data-template-picker]");
  if (!picker) return;

  var textarea = document.querySelector("[data-md-editor] textarea");
  if (!textarea) return;

  picker.addEventListener("click", function (event) {
    var button = event.target.closest("[data-template]");
    if (!button) return;

    var body = TEMPLATES[button.getAttribute("data-template")];
    if (!body) return;

    var prefix = textarea.value.trim();
    textarea.value = prefix ? prefix + "\n\n" + body : body;
    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    textarea.dispatchEvent(new Event("input"));

    if (window.LL && window.LL.toast) {
      window.LL.toast("已填入「" + button.textContent.trim() + "」模板");
    }
  });
})();
