import { expect, test } from "vitest";
import { jobStageLabel } from "./jobProgress";

test.each([
  ["document_batching", "按页顺序解析并保存批次检查点"],
  ["document_repairing", "正在修复当前批次的返回格式"],
  ["document_boundary", "正在复核相邻批次的截断与续接"],
])("labels the %s phase", (stage, label) => {
  expect(jobStageLabel({ kind: "llm_document_parse", stage })).toBe(label);
});

test("does not echo an unknown phase", () => {
  expect(jobStageLabel({ kind: "llm_document_parse", stage: "private" })).toBe(
    "正在处理",
  );
  expect(jobStageLabel({ kind: "llm_document_parse", stage: "toString" })).toBe(
    "正在处理",
  );
});
