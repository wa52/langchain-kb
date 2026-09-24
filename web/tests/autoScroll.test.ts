import assert from "node:assert/strict";
import test from "node:test";

import { isNearBottom, scrollToBottomIfFollowing } from "../src/components/chat/autoScroll.ts";

test("keeps the message list at the bottom while following", () => {
  const element = { scrollTop: 120, scrollHeight: 860 };

  assert.equal(scrollToBottomIfFollowing(element, true), true);
  assert.equal(element.scrollTop, 860);
});

test("does not take the user back to the bottom after they scroll up", () => {
  const element = { scrollTop: 120, scrollHeight: 860 };

  assert.equal(scrollToBottomIfFollowing(element, false), false);
  assert.equal(element.scrollTop, 120);
});

test("considers a list near the bottom within the follow threshold", () => {
  assert.equal(isNearBottom({ scrollTop: 730, scrollHeight: 860, clientHeight: 100 }), true);
  assert.equal(isNearBottom({ scrollTop: 700, scrollHeight: 860, clientHeight: 100 }), false);
});
