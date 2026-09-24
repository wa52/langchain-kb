export interface ScrollMetrics {
  scrollTop: number;
  scrollHeight: number;
  clientHeight?: number;
}

const FOLLOW_THRESHOLD_PX = 48;

export function isNearBottom(
  element: ScrollMetrics,
  threshold = FOLLOW_THRESHOLD_PX,
): boolean {
  return element.scrollHeight - element.scrollTop - (element.clientHeight ?? 0) <= threshold;
}

export function scrollToBottomIfFollowing(
  element: Pick<ScrollMetrics, "scrollTop" | "scrollHeight"> | null,
  shouldFollow: boolean,
): boolean {
  if (!element || !shouldFollow) return false;
  element.scrollTop = element.scrollHeight;
  return true;
}
