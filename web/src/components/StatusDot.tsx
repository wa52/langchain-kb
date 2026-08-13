const STATE_LABEL: Record<string, string> = {
  ready: "就绪",
  loading: "加载中",
  error: "错误",
  degraded: "降级",
  disabled: "关闭",
  pending: "待启动",
};

export function StatusDot({ state }: { state: string }) {
  const label = STATE_LABEL[state] ?? state;
  return (
    <span className={`dot ${state}`} role="img" aria-label={`状态：${label}`} />
  );
}
