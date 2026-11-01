/**
 * 看板的纯逻辑部分：事件归类、指标增量、时间格式化。
 *
 * 这些函数不依赖 Vue，单独抽出来便于单元测试，也避免组件里堆逻辑。
 */

/** 按事件类型归类，用于筛选。 */
export function bucketOf(kind) {
  if (!kind) return "other";
  const head = String(kind).split("_")[0];
  return ["entry", "session", "card", "todo", "topic"].includes(head) ? head : "other";
}

/** 计算一次事件对指标的影响。 */
export function applyMetrics(current, event) {
  const metrics = { ...current };
  const kind = event?.kind;
  if (kind === "entry_created" || kind === "entry_updated") {
    metrics.entries = (metrics.entries || 0) + (kind === "entry_created" ? 1 : 0);
  } else if (kind === "session_ended") {
    const minutes = (event?.payload || {}).minutes || 0;
    metrics.minutes = (metrics.minutes || 0) + minutes;
  } else if (kind === "todo_toggled") {
    const done = (event?.payload || {}).done;
    metrics.todos = Math.max(0, (metrics.todos || 0) + (done ? -1 : 1));
  }
  return metrics;
}

/** 把事件列表按类型分桶计数。 */
export function countByBucket(events) {
  const counts = {};
  for (const event of events || []) {
    const key = bucketOf(event.kind);
    counts[key] = (counts[key] || 0) + 1;
  }
  return counts;
}

/** 按当前筛选过滤事件。 */
export function filterEvents(events, activeKind) {
  if (!activeKind || activeKind === "all") return events || [];
  return (events || []).filter((event) => bucketOf(event.kind) === activeKind);
}

/** 新的事件插到最前，并限制条数。 */
export function prependEvent(events, event, limit = 50) {
  return [event, ...(events || [])].slice(0, limit);
}

/** 相对时间：刚刚 / N 秒前 / N 分钟前 / N 小时前 / 日期。 */
export function relativeTime(value, now = Date.now()) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const diff = Math.floor((now - date.getTime()) / 1000);
  if (diff < 5) return "刚刚";
  if (diff < 60) return `${diff} 秒前`;
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return date.toLocaleDateString("zh-CN");
}

/** 时分秒显示。 */
export function clockTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** 把时长换成人话。 */
export function durationText(minutes) {
  const value = Number(minutes || 0);
  const hours = Math.floor(value / 60);
  const rest = value % 60;
  if (hours && rest) return `${hours} 小时 ${rest} 分`;
  if (hours) return `${hours} 小时`;
  return `${rest} 分钟`;
}

/**
 * 图表柱子的高度：按峰值等比缩放，最低 4 像素。
 */
export function barHeights(series, maxBar = 96) {
  const rows = series || [];
  if (!rows.length) return [];
  const peak = Math.max(...rows.map((row) => Number(row.count || 0)), 1);
  return rows.map((row) => ({
    ...row,
    height: Math.max(4, Math.round((Number(row.count || 0) / peak) * maxBar)),
  }));
}
