/* 专注计时器：番茄钟逻辑 + 结束后写入学习会话。 */
(function () {
  var MODES = {
    focus: { label: "专注", minutes: 25 },
    rest: { label: "休息", minutes: 5 },
  };
  var CIRCUMFERENCE = 2 * Math.PI * 96;

  var root = document.querySelector("[data-focus-dial]");
  if (!root) return;

  var form = document.querySelector("[data-focus-form]");
  var timeEl = document.querySelector("[data-focus-time]");
  var modeEl = document.querySelector("[data-focus-mode]");
  var ring = document.querySelector("[data-focus-ring]");
  var startBtn = document.querySelector("[data-focus-start]");
  var resetBtn = document.querySelector("[data-focus-reset]");
  var saveBtn = document.querySelector("[data-focus-save]");
  var hintEl = document.querySelector("[data-focus-hint]");
  var minutesInput = document.querySelector("[data-focus-minutes]");

  var mode = "focus";
  var total = MODES.focus.minutes * 60;
  var remain = total;
  var timer = null;
  var finishedMinutes = 0;

  ring.setAttribute("stroke-dasharray", CIRCUMFERENCE.toFixed(1));

  function render() {
    var minutes = Math.floor(remain / 60);
    var seconds = remain % 60;
    timeEl.textContent =
      String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0");
    var ratio = total ? remain / total : 0;
    ring.setAttribute(
      "stroke-dashoffset",
      (CIRCUMFERENCE * (1 - ratio)).toFixed(1)
    );
    document.body.classList.toggle("is-focusing", !!timer && mode === "focus");
  }

  function stop() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  function switchMode(next) {
    mode = next;
    total = MODES[mode].minutes * 60;
    remain = total;
    modeEl.textContent = MODES[mode].label;
    render();
  }

  function finish() {
    stop();
    if (mode === "focus") {
      finishedMinutes = MODES.focus.minutes;
      minutesInput.value = finishedMinutes;
      saveBtn.classList.remove("hidden");
      hintEl.textContent = "专注完成，点击按钮把这段时间记到所选主题。";
    } else {
      hintEl.textContent = "休息结束，可以开始下一个番茄钟。";
    }
    startBtn.disabled = false;
    resetBtn.disabled = false;
    startBtn.textContent = mode === "focus" ? "再专注一轮" : "开始休息";
  }

  startBtn.addEventListener("click", function () {
    if (timer) {
      stop();
      startBtn.textContent = "继续";
      resetBtn.disabled = false;
      return;
    }
    startBtn.textContent = "暂停";
    resetBtn.disabled = false;
    saveBtn.classList.add("hidden");
    hintEl.textContent = "计时中，保持专注…";
    timer = setInterval(function () {
      remain -= 1;
      if (remain <= 0) {
        remain = 0;
        render();
        finish();
        return;
      }
      render();
    }, 1000);
  });

  resetBtn.addEventListener("click", function () {
    stop();
    switchMode("focus");
    startBtn.textContent = "开始专注";
    startBtn.disabled = false;
    resetBtn.disabled = true;
    saveBtn.classList.add("hidden");
    hintEl.textContent = "计时结束后点击「记录本次专注」，时间会写入学习会话并进入统计。";
  });

  saveBtn.addEventListener("click", function () {
    if (!form) return;
    var data = new FormData(form);
    saveBtn.disabled = true;
    fetch(form.action, {
      method: "POST",
      body: data,
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin",
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (payload) {
        if (payload && payload.ok) {
          hintEl.textContent = payload.message;
          saveBtn.classList.add("hidden");
          switchMode("rest");
          startBtn.textContent = "开始休息";
          if (window.LL && window.LL.toast) window.LL.toast(payload.message);
        } else {
          hintEl.textContent = (payload && payload.error) || "记录失败，请重试。";
        }
      })
      .catch(function () {
        hintEl.textContent = "网络异常，未能记录本次专注。";
      })
      .finally(function () {
        saveBtn.disabled = false;
      });
  });

  render();
})();
