/* 笔记编辑器：Markdown 工具条 + 实时预览。
   预览渲染只覆盖笔记里常用的语法，保持零依赖。 */
(function () {
  var wrappers = document.querySelectorAll("[data-md-editor]");
  if (!wrappers.length) return;

  var ESCAPE = { "&": "&amp;", "<": "&lt;", ">": "&gt;" };

  function escapeHtml(text) {
    return String(text).replace(/[&<>]/g, function (char) {
      return ESCAPE[char];
    });
  }

  function inline(text) {
    var out = escapeHtml(text);
    out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
    out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
    out = out.replace(/~~([^~]+)~~/g, "<del>$1</del>");
    out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, function (_, label, href) {
      var safe = /^(https?:|#|\/)/i.test(href) ? href : "#";
      return '<a href="' + safe + '" rel="noopener noreferrer">' + label + "</a>";
    });
    return out;
  }

  function render(markdown) {
    var lines = String(markdown || "").split(/\r?\n/);
    var html = "";
    var listType = null;
    var inCode = false;

    function closeList() {
      if (listType) {
        html += "</" + listType + ">";
        listType = null;
      }
    }

    lines.forEach(function (raw) {
      var line = raw;

      if (/^```/.test(line.trim())) {
        closeList();
        html += inCode ? "</code></pre>" : '<pre class="md-code"><code>';
        inCode = !inCode;
        return;
      }
      if (inCode) {
        html += escapeHtml(line) + "\n";
        return;
      }
      if (!line.trim()) {
        closeList();
        return;
      }

      var heading = line.match(/^(#{1,6})\s+(.*)$/);
      if (heading) {
        closeList();
        var level = heading[1].length;
        html += "<h" + level + ">" + inline(heading[2]) + "</h" + level + ">";
        return;
      }

      var quote = line.match(/^>\s?(.*)$/);
      if (quote) {
        closeList();
        html += "<blockquote>" + inline(quote[1]) + "</blockquote>";
        return;
      }

      var task = line.match(/^\s*[-*]\s+\[([ xX])\]\s+(.*)$/);
      if (task) {
        if (listType !== "ul") {
          closeList();
          html += '<ul class="md-tasks">';
          listType = "ul";
        }
        var checked = task[1].toLowerCase() === "x" ? " checked" : "";
        html +=
          '<li class="md-task"><input type="checkbox" disabled' +
          checked +
          " /> " +
          inline(task[2]) +
          "</li>";
        return;
      }

      var item = line.match(/^\s*([-*]|\d+\.)\s+(.*)$/);
      if (item) {
        var wanted = /\d/.test(item[1][0]) ? "ol" : "ul";
        if (listType !== wanted) {
          closeList();
          html += "<" + wanted + ">";
          listType = wanted;
        }
        html += "<li>" + inline(item[2]) + "</li>";
        return;
      }

      closeList();
      html += "<p>" + inline(line) + "</p>";
    });

    closeList();
    if (inCode) html += "</code></pre>";
    return html;
  }

  wrappers.forEach(function (wrapper) {
    var textarea = wrapper.querySelector("textarea");
    var preview = wrapper.querySelector("[data-md-preview]");
    if (!textarea) return;

    function refresh() {
      if (!preview) return;
      if (preview.hidden) return;
      preview.innerHTML = render(textarea.value) || '<p class="muted">还没有内容</p>';
    }

    wrapper.querySelectorAll("[data-md-action]").forEach(function (button) {
      button.addEventListener("click", function () {
        var action = button.getAttribute("data-md-action");
        var start = textarea.selectionStart;
        var end = textarea.selectionEnd;
        var value = textarea.value;
        var selected = value.slice(start, end);
        var before = value.slice(0, start);
        var after = value.slice(end);
        var body = selected;
        var prefix = "";
        var suffix = "";

        if (action === "bold") {
          prefix = suffix = "**";
          body = body || "重点";
        } else if (action === "code") {
          prefix = suffix = "`";
          body = body || "code";
        } else if (action === "heading") {
          prefix = "## ";
          body = body || "小节标题";
        } else if (action === "list") {
          prefix = "- ";
          body = body || "要点";
        } else if (action === "task") {
          prefix = "- [ ] ";
          body = body || "待办事项";
        } else if (action === "quote") {
          prefix = "> ";
          body = body || "引用或结论";
        }

        textarea.value = before + prefix + body + suffix + after;
        textarea.focus();
        textarea.setSelectionRange(start + prefix.length, start + prefix.length + body.length);
        textarea.dispatchEvent(new Event("input"));
      });
    });

    var toggle = wrapper.querySelector("[data-md-toggle]");
    if (toggle && preview) {
      toggle.addEventListener("click", function () {
        preview.hidden = !preview.hidden;
        toggle.textContent = preview.hidden ? "预览" : "关闭预览";
        toggle.classList.toggle("btn--primary", !preview.hidden);
        refresh();
      });
    }

    if (preview) {
      textarea.addEventListener("input", refresh);
    }
  });
})();
