import { test, expect } from "@playwright/test";

test("P5 scanning shows preparation, object completion and dependency rebuilding as separate phases", async ({
  page,
}) => {
  await page.goto("/e2e/p5.html?lintPhases=1");
  await page.getByRole("button", { name: "开始规则扫描" }).click();
  const preparation = page.getByRole("progressbar", { name: "扫描准备进度" });
  await expect(preparation).toBeVisible();
  await expect(preparation).not.toHaveAttribute("value");
  await expect(page.getByText("检查总数待定")).toBeVisible();
  expect(
    await page.evaluate(() =>
      window.p5Harness.requests.filter((r) => r.path.endsWith("/advance")),
    ),
  ).toEqual([]);
  await page.evaluate(() => window.p5Harness.finishLintPreparation?.());

  await expect(
    page.getByText("正在重建依赖索引", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("progressbar", { name: "对象检查进度" }),
  ).toHaveAttribute("value", "25");
  const dependencies = page.getByRole("progressbar", {
    name: "扫描依赖索引重建进度",
  });
  await expect(dependencies).toBeVisible();
  await expect(dependencies).not.toHaveAttribute("value");
  await expect(page.getByText("检查完成", { exact: true })).toHaveCount(0);
  await expect(
    page.getByText("对象检查已完成，正在重建依赖索引；完成后才结束本轮扫描。"),
  ).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          window.p5Harness.requests.filter((r) => r.path.endsWith("/advance"))
            .length,
      ),
    )
    .toBe(2);
  await page.evaluate(() => window.p5Harness.finishLintRebuild?.());
  await expect(page.getByText("检查完成", { exact: true })).toBeVisible();
  await expect(dependencies).toHaveCount(0);
  await page.getByText("阶段耗时", { exact: true }).click();
  await expect(page.getByText("0.025 秒", { exact: true })).toBeVisible();
  await expect(page.getByText("0.200 秒", { exact: true })).toBeVisible();
  await expect(page.getByText("2 次", { exact: true })).toBeVisible();
  expect(
    await page.evaluate(() =>
      window.p5Harness.requests.filter((r) =>
        /generate|materialize|publish/.test(r.path),
      ),
    ),
  ).toEqual([]);
  expect(await page.evaluate(() => window.p5Harness.unexpected)).toEqual([]);
});

test("P5 rules, dependency navigation and explicit index repair render without model work", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/e2e/p5.html");
  await page.getByText("检查文档范围 · 全部可用文档").click();
  await page.getByLabel("检查文档 · 合成阅读草稿").check();
  await page.getByRole("button", { name: "开始规则扫描" }).click();
  expect(
    await page.evaluate(
      () =>
        window.p5Harness.requests.find(
          (r) => r.path.endsWith("/lint/runs") && r.method === "POST",
        )?.body?.document_ids,
    ),
  ).toEqual(["page-1"]);
  expect(
    await page.evaluate(
      () =>
        window.p5Harness.requests.find((r) =>
          r.path.endsWith("/lint/runs/lint-1/advance"),
        )?.body,
    ),
  ).toEqual({ max_items: 100 });
  await expect(
    page.getByText("已检查 25 / 25 个对象 · 规则 synthetic-rules-1"),
  ).toBeVisible();
  await expect(
    page.getByText("合成来源已变化，仅定位受影响内容。"),
  ).toBeVisible();
  const plan = page.getByRole("region", { name: "Lint 修复或处理方案" });
  await expect(plan.getByText("修复 / 处理方案")).toBeVisible();
  await expect(
    plan.getByText("先回查来源与条件，再通过受控流程处理受影响内容。"),
  ).toBeVisible();
  const sourceStep = plan.getByRole("listitem").filter({
    has: page.getByText("核对原文与来源状态", { exact: true }),
  });
  const rebuildStep = plan.getByRole("listitem").filter({
    has: page.getByText("有明确证据时创建新版本", { exact: true }),
  });
  await expect(
    sourceStep.getByText("需要用户确认 · 此步骤不调用模型"),
  ).toBeVisible();
  await expect(
    rebuildStep.getByText("需要用户确认 · 由后续受控流程决定"),
  ).toBeVisible();
  await expect(
    plan.getByText(
      /没有明确条件证据时保留 unknown，不推断 conflicting，也不补造条件/,
    ),
  ).toBeVisible();
  await expect(plan.getByRole("button")).toHaveCount(0);
  await page.getByRole("button", { name: "在知识图谱中定位" }).click();
  await expect(page.getByText("图谱定位：node-1")).toBeVisible();
  await page.getByText("查看依赖与影响范围").click();
  await expect(
    page.getByRole("button", { name: "查看关联文档" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "重建派生依赖索引" }).click();
  await expect(
    page.getByText("依赖索引已重建，共 7 条依赖；检测到 1 项变化。"),
  ).toBeVisible();
  expect(
    await page.evaluate(() =>
      window.p5Harness.requests.filter((r) =>
        /generate|materialize|publish/.test(r.path),
      ),
    ),
  ).toEqual([]);
  expect(await page.evaluate(() => window.p5Harness.unexpected)).toEqual([]);
  expect(errors).toEqual([]);
});

test("P5 explicit comment permission, source selection and read-only external registration render", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/e2e/p5.html");
  await page.getByRole("button", { name: "Wiki 测试页" }).click();
  await page.getByLabel("Wiki 主题或问题").fill("合成方法比较");
  await page.getByLabel("包含已独立授权的个人笔记、批注评论与外部资料").check();
  const comment = page.getByLabel("模型来源 · 合成个人评论");
  await expect(comment).toBeDisabled();
  await page
    .getByRole("button", { name: "独立授权模型使用 · 合成个人评论" })
    .click();
  await expect(comment).toBeEnabled();
  await expect(comment).not.toBeChecked();
  const consent = page.getByLabel("允许本次主题阅读整理发送必要来源给模型");
  await consent.check();
  await comment.check();
  await expect(consent).not.toBeChecked();
  await page.getByLabel("查看并登记已授权的外部 Markdown").check();
  await page.getByLabel("外部材料读取目录").selectOption("read-root");
  await page.getByLabel("外部 Markdown 文件").selectOption("synthetic.md");
  await page.getByRole("button", { name: "只读预览外部 Markdown" }).click();
  await page.getByLabel("外部材料标题").fill("合成外部阅读材料");
  await page.getByRole("button", { name: "登记外部阅读材料" }).click();
  await expect(
    page.getByText("外部材料快照已登记，科学来源仍未核验。"),
  ).toBeVisible();
  const external = page.getByLabel("模型来源 · 合成外部阅读材料");
  await expect(external).not.toBeChecked();
  await external.check();
  await consent.check();
  await page.getByRole("button", { name: "生成有据整理", exact: true }).click();
  const prepare = await page.evaluate(() =>
    window.p5Harness.requests.find((r) =>
      r.path.endsWith("/workflows/prepare"),
    ),
  );
  expect(prepare?.body?.personal_sources).toEqual({
    version: "p5-personal-sources-1",
    note_ids: [],
    annotation_ids: ["annotation-1"],
    external_version_ids: ["external-v1"],
  });
  const register = await page.evaluate(() =>
    window.p5Harness.requests.find(
      (r) => r.method === "POST" && r.path.includes("/external-documents?"),
    ),
  );
  expect(register?.body?.expected_sha256).toBe("d".repeat(64));
  await page
    .getByRole("button", { name: "撤销批注本地读取权限 · 合成个人评论" })
    .click();
  const redacted = page.getByLabel("模型来源 · 已撤销本地读取的批注");
  await expect(redacted).toBeDisabled();
  await expect(redacted).not.toBeChecked();
  await expect(
    page.getByText("本地读取权限已撤销，评论正文和定位均已隐藏。"),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "允许本地读取批注 · 已撤销本地读取的批注" })
    .click();
  await expect(comment).toBeEnabled();
  await expect(comment).not.toBeChecked();
  expect(
    await page.evaluate(() =>
      window.p5Harness.requests.filter((r) => r.path.endsWith("/publish")),
    ),
  ).toEqual([]);
  expect(await page.evaluate(() => window.p5Harness.unexpected)).toEqual([]);
  expect(errors).toEqual([]);
});

test("P5 Wiki draft, save and native authorization remain separate from publication across reload", async ({
  page,
}) => {
  await page.goto("/e2e/p5.html");
  await page.getByRole("button", { name: "Wiki 测试页" }).click();
  await page.getByLabel("Wiki 主题或问题").fill("合成方法条件");
  const consent = page.getByLabel("允许本次主题阅读整理发送必要来源给模型");
  await consent.check();
  await page.getByLabel("Wiki 主题或问题").fill("更新主题");
  await expect(consent).not.toBeChecked();
  await page.getByLabel("Wiki 主题或问题").fill("合成方法条件");
  await consent.check();
  await page.getByRole("button", { name: "生成有据整理", exact: true }).click();
  await page.getByRole("button", { name: "创建内部整理草稿" }).click();
  await expect(
    page.getByRole("heading", { name: "方法与条件" }).last(),
  ).toBeVisible();
  expect(
    await page.evaluate(() =>
      window.p5Harness.requests.filter((r) => r.path.endsWith("/publish")),
    ),
  ).toEqual([]);
  await page.getByRole("button", { name: "保存内部版本" }).click();
  await expect(page.getByText("内部版本已保存。")).toBeVisible();
  await page.getByRole("button", { name: "选择并授权独立导出目录" }).click();
  await page
    .getByRole("button", { name: "导出 Markdown", exact: true })
    .click();
  await expect(page.getByText("导出状态：生成完成")).toBeVisible();
  expect(await page.evaluate(() => window.p5Harness.authorizations)).toBe(1);
  const publish = await page.evaluate(() =>
    window.p5Harness.requests.find((r) => r.path.endsWith("/publish")),
  );
  expect(publish?.body?.expected_target_hash).toBeNull();
  expect(publish?.body?.root_id).toBe("root-1");
  await page.reload();
  await page.getByRole("button", { name: "Wiki 测试页" }).click();
  await expect(
    page.getByRole("heading", { name: "方法与条件" }).last(),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "更新导出 Markdown" }),
  ).toBeDisabled();
  expect(
    await page.evaluate(() =>
      window.p5Harness.requests.filter((r) => r.method === "POST"),
    ),
  ).toEqual([]);
  expect(await page.evaluate(() => window.p5Harness.unexpected)).toEqual([]);
});

test("P5 external-edit snapshot and interrupted-publication recovery preserve the conflict", async ({
  page,
}) => {
  await page.goto("/e2e/p5.html?conflict=1");
  await page.getByLabel("Wiki 导出目录").selectOption("root-1");
  await expect(
    page.getByRole("button", { name: "更新导出 Markdown" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "只读查看外部修改与差异" }).click();
  await page.getByText("外部修改快照与差异 · 未验证来源").click();
  await expect(
    page.getByText("外部私人修改，未验证来源。", { exact: true }),
  ).toBeVisible();
  await page.getByText("导出操作记录与中断恢复").click();
  await page.getByRole("button", { name: /导出操作 1/ }).click();
  expect(
    await page.evaluate(() =>
      window.p5Harness.requests.filter((r) => r.path.endsWith("/recover")),
    ),
  ).toEqual([]);
  await page.getByRole("button", { name: "核对并恢复这次导出" }).click();
  await expect(page.getByText("导出状态：文件冲突")).toBeVisible();
  expect(
    await page.evaluate(() =>
      window.p5Harness.requests.filter((r) => r.path.endsWith("/publish")),
    ),
  ).toEqual([]);
  expect(await page.evaluate(() => window.p5Harness.unexpected)).toEqual([]);
});
