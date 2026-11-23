import { expect, test } from "@playwright/test";

test("task records show knowledge failure details and legacy uncertainty without rendering raw content or retrying", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    const base = {
      project_id: "project-1",
      status: "failed",
      stage: "failed",
      attempt: 1,
      error: "KNOWLEDGE_RESPONSE_INVALID",
      created_at: "2026-11-20T00:00:00Z",
      updated_at: "2026-11-20T00:00:01Z",
    };
    localStorage.setItem(
      "kb-fixture:jobs",
      JSON.stringify([
        {
          ...base,
          id: "knowledge-schema",
          kind: "knowledge_extract",
          result: {
            knowledge_diagnostic: {
              version: "knowledge-diagnostic-1",
              code: "KNOWLEDGE_RESPONSE_INVALID",
              category: "schema",
              summary: "返回内容缺少必需字段，知识版本未保存。",
              issues: [
                {
                  path: "$.nodes[0].type",
                  code: "missing",
                  message: "缺少必需字段。",
                },
              ],
              request_sent: true,
              raw_available: true,
              action: "原始响应已保留，请核对诊断后决定是否显式继续。",
              raw_response: "PRIVATE_RAW_RESPONSE",
            },
            raw_response: "PRIVATE_TOP_LEVEL_RAW",
          },
        },
        {
          ...base,
          id: "knowledge-legacy",
          kind: "knowledge_connect",
          result: {
            knowledge_diagnostic: {
              version: "knowledge-diagnostic-1",
              code: "KNOWLEDGE_RESPONSE_INVALID",
              category: "unknown",
              summary: "旧任务没有保留失败细节，无法判定具体原因。",
              issues: [],
              request_sent: true,
              raw_available: false,
              action: "保留失败记录；决定继续前请确认模型配置和请求预算。",
            },
          },
        },
      ]),
    );
  });
  await page.goto("/e2e/knowledge.html");
  await page.getByRole("button", { name: "任务记录", exact: true }).click();
  const schema = page.locator("#job-knowledge-schema");
  const legacy = page.locator("#job-knowledge-legacy");
  await expect(
    schema.getByText("返回内容缺少必需字段，知识版本未保存。"),
  ).toBeVisible();
  await expect(schema.getByText("$.nodes[0].type")).toBeHidden();
  await schema.getByText("诊断详情", { exact: true }).click();
  await expect(schema.getByText("$.nodes[0].type")).toBeVisible();
  await expect(schema.getByText(/发送记录：已标记；费用未知/)).toContainText(
    "原始响应：已在本机保留",
  );
  await expect(legacy.getByText("失败原因 · 原因未确定")).toBeVisible();
  await expect(legacy.getByText(/无法判定具体原因/)).toBeVisible();
  await legacy.getByText("诊断详情", { exact: true }).click();
  await expect(legacy.getByText(/原始响应：没有可检查的响应/)).toBeVisible();
  await expect(page.getByText(/PRIVATE_/)).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /重试本地处理|格式修复/ }),
  ).toHaveCount(0);
  await expect(page.getByText(/到研究内容知识库查看原因/)).toHaveCount(0);
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
  }
  await page.screenshot({
    path: testInfo.outputPath("knowledge-task-diagnostics.png"),
    fullPage: true,
  });
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
  expect(await page.evaluate(() => window.__knowledgeJobActions)).toEqual([]);
  expect(errors).toEqual([]);
});

test("knowledge navigation, real graph, report and both source chains form a read-only loop", async ({
  page,
}, testInfo) => {
  const errors: string[] = [],
    external: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (!request.url().startsWith("http://127.0.0.1:1427/"))
      external.push(request.url());
  });
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.goto("/e2e/knowledge.html");
  const nav = page.getByRole("navigation", { name: "主导航" });
  await expect(nav.getByRole("button")).toHaveText([
    "研究项目1",
    "研究内容知识库",
    "任务记录",
    "归档管理",
  ]);
  await nav
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await expect(nav.getByLabel("1 份未读联系汇报")).toBeVisible();
  await page.getByRole("button", { name: "知识地图", exact: true }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(12);
  const root = page.locator('.react-flow__node[data-id="paper:library-A"]');
  await root.click();
  await expect(page.locator(".react-flow__node")).toHaveCount(12);
  await page.getByRole("button", { name: "聚焦图谱", exact: true }).click();
  await page
    .locator('.react-flow__node[data-id="version:version-A:A-2"]')
    .click();
  await page.getByText("本地解析材料 · 第 2 页 · 章节 合成方法章节").click();
  await expect(page.getByText("A synthetic source text.")).toBeVisible();
  const edge = page.locator('.react-flow__edge[data-id="cross:relation-1"]');
  await expect(edge.locator(".react-flow__edge-path")).toHaveCSS(
    "stroke-dasharray",
    "4px, 5px",
  );
  await edge.click({ force: true });
  await page.getByRole("button", { name: "打开对应联系汇报" }).click();
  const dialog = page.getByRole("dialog", { name: "联系汇报" });
  await expect(dialog.getByText("新增论文依据")).toBeVisible();
  await expect(dialog.getByText("已有论文依据")).toBeVisible();
  await expect(dialog.getByText(/任务条件不同/)).toBeVisible();
  await dialog.getByText("模型提取材料 · 章节 模型方法章节").click();
  await expect(dialog.getByText("A synthetic source text.")).toBeVisible();
  await dialog.getByRole("button", { name: "置顶汇报", exact: true }).click();
  await dialog.getByLabel("汇报个人备注").fill("需要核查任务条件");
  await dialog.getByRole("button", { name: "保存汇报备注" }).click();
  await expect
    .poll(async () =>
      page.evaluate(
        () => JSON.parse(localStorage.getItem("kb-fixture:report")!).note,
      ),
    )
    .toBe("需要核查任务条件");
  await page.screenshot({ path: testInfo.outputPath("knowledge-report.png") });
  await dialog
    .getByRole("button", { name: "在知识地图中定位这条联系" })
    .click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByLabel("展开论文")).toHaveValue("all");
  await expect(
    page.getByRole("button", { name: "打开对应联系汇报" }),
  ).toBeVisible();
  await expect(page.locator(".react-flow__node")).toHaveCount(12);
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test("saved report metadata, camera and fixed nodes survive reload and narrow layouts", async ({
  page,
}) => {
  await page.goto("/e2e/knowledge.html");
  await page
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await page
    .getByRole("button", { name: /合成论文 B 与已有研究的联系/ })
    .click();
  await page.getByLabel("汇报个人备注").fill("长期保存的个人判断");
  await page.getByRole("button", { name: "保存汇报备注" }).click();
  await page.getByRole("button", { name: "置顶汇报", exact: true }).click();
  await page.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByRole("button", { name: "知识地图", exact: true }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(12);
  await page.locator(".react-flow__controls-zoomin").click();
  await expect
    .poll(async () => page.evaluate(() => window.__knowledgeLayoutWrites))
    .toBeGreaterThan(0);
  const before = await page.evaluate(
    () =>
      JSON.parse(localStorage.getItem("kb-fixture:layout:library:all:all")!)
        .layout.viewport,
  );
  await page.getByRole("button", { name: "联系汇报", exact: true }).click();
  await page.getByRole("button", { name: "知识地图", exact: true }).click();
  await expect
    .poll(async () =>
      page
        .locator(".react-flow__viewport")
        .evaluate(
          (element) =>
            new DOMMatrixReadOnly(getComputedStyle(element).transform).a,
        ),
    )
    .toBeCloseTo(before.zoom, 2);
  await page.reload();
  await page
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await expect(
    page.locator('.react-flow__node[data-id="paper:library-A"]'),
  ).toHaveClass(/pinned/);
  const camera = await page
    .locator(".react-flow__viewport")
    .evaluate((element) => {
      const matrix = new DOMMatrixReadOnly(getComputedStyle(element).transform);
      return { x: matrix.e, y: matrix.f, zoom: matrix.a };
    });
  expect(camera.x).toBeCloseTo(before.x, 2);
  expect(camera.y).toBeCloseTo(before.y, 2);
  expect(camera.zoom).toBeCloseTo(before.zoom, 2);
  await page.getByRole("button", { name: "联系汇报", exact: true }).click();
  await page
    .getByRole("button", { name: /合成论文 B 与已有研究的联系/ })
    .click();
  await expect(page.getByLabel("汇报个人备注")).toHaveValue(
    "长期保存的个人判断",
  );
  await expect(page.getByRole("button", { name: "取消置顶" })).toBeVisible();
  await page.getByRole("button", { name: "关闭", exact: true }).click();
  for (const width of [620, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBe(true);
    await page.getByRole("button", { name: "知识地图", exact: true }).click();
    await expect(page.locator(".react-flow__node")).toHaveCount(12);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBe(true);
  }
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
});

test("only an explicit selected source and consent can submit a knowledge model task", async ({
  page,
}) => {
  await page.goto("/e2e/knowledge.html");
  await page
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await page
    .getByRole("button", { name: "加入论文知识", exact: true })
    .first()
    .click();
  await page.getByLabel("选择入库论文").selectOption("paper-A");
  await page.getByLabel("选择知识来源").selectOption("model_parse:parse-A");
  await expect(
    page.getByRole("button", { name: "生成带来源知识", exact: true }),
  ).toBeDisabled();
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
  await page
    .getByRole("checkbox", { name: /允许向已配置模型发送此来源版本/ })
    .check();
  await page
    .getByRole("button", { name: "生成带来源知识", exact: true })
    .click();
  await expect
    .poll(async () => page.evaluate(() => window.__knowledgeModelCalls))
    .toEqual([
      {
        kind: "extract",
        paper_id: "paper-A",
        source_kind: "model_parse",
        source_id: "parse-A",
        allow_network: true,
      },
    ]);
});

test("all three unlimited budgets persist across reload without model requests and fit narrow screens", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/e2e/knowledge.html");
  await page
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await page.getByRole("button", { name: "自动分析设置", exact: true }).click();
  for (const [label, finite] of [
    ["单次输入 Token 预算", "96000"],
    ["单次输出 Token 预算", "12000"],
    ["每次分析最多请求数", "4"],
  ]) {
    const input = page.getByRole("spinbutton", { name: label, exact: true });
    const unlimited = page.getByRole("checkbox", { name: `${label}无上限` });
    await input.fill(finite);
    await unlimited.check();
    await expect(input).toBeDisabled();
    await expect(input).toHaveValue("");
    await unlimited.uncheck();
    await expect(input).toHaveValue(finite);
    await unlimited.check();
  }
  await page.getByRole("button", { name: "保存分析策略", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "自动分析设置" }),
  ).not.toBeVisible();
  const stored = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("kb-fixture:settings")!),
  );
  expect(stored).toMatchObject({
    max_input_tokens: null,
    max_output_tokens: null,
    max_requests_per_run: null,
  });
  expect(stored.total_request_limit).toBeGreaterThan(0);
  await page.reload();
  await page
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await page.getByRole("button", { name: "自动分析设置", exact: true }).click();
  for (const label of [
    "单次输入 Token 预算",
    "单次输出 Token 预算",
    "每次分析最多请求数",
  ]) {
    await expect(
      page.getByRole("checkbox", { name: `${label}无上限` }),
    ).toBeChecked();
    await expect(
      page.getByRole("spinbutton", { name: label, exact: true }),
    ).toBeDisabled();
  }
  for (const width of [620, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const dialog = page.getByRole("dialog", { name: "自动分析设置" });
    expect(
      await dialog.evaluate(
        (element) => element.scrollWidth <= element.clientWidth + 1,
      ),
    ).toBe(true);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBe(true);
  }
  await page.screenshot({
    path: testInfo.outputPath("knowledge-unlimited-budgets.png"),
  });
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
  expect(errors).toEqual([]);
});

test("knowledge local recovery requires review and explicit confirmation without model calls", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    localStorage.setItem(
      "kb-fixture:runs",
      JSON.stringify({
        items: [
          {
            id: "failed-recovery-run",
            job_id: "failed-recovery-job",
            kind: "extract",
            status: "failed",
            request_count: 1,
            max_requests: 2,
            error_code: "KNOWLEDGE_RESPONSE_SCHEMA_INVALID",
            error: "KNOWLEDGE_RESPONSE_SCHEMA_INVALID",
            created_at: "2026-11-21T00:00:00Z",
            local_recovery: {
              version: "knowledge-local-recovery-1",
              available: true,
              preview_fingerprint: "list-preview",
              original_nodes: 19,
              original_edges: 20,
              kept_nodes: 19,
              kept_edges: 9,
              excluded_edges: [],
            },
          },
        ],
        total: 1,
      }),
    );
    localStorage.setItem(
      "kb-fixture:jobs",
      JSON.stringify([
        {
          id: "failed-recovery-job",
          kind: "knowledge_extract",
          project_id: "project-1",
          status: "failed",
          stage: "failed",
          attempt: 1,
          error: "KNOWLEDGE_RESPONSE_SCHEMA_INVALID",
          result: {
            knowledge_diagnostic: {
              version: "knowledge-diagnostic-1",
              code: "KNOWLEDGE_RESPONSE_SCHEMA_INVALID",
              category: "schema",
              summary: "关系端点类型或方向未通过图谱规则。",
              action: "检查逐条关系后决定是否显式本机恢复。",
              request_sent: true,
              raw_available: true,
              issue_count: 1,
              issues: [
                {
                  path: "graph.edges[9].type",
                  code: "invalid_relation_types",
                  message:
                    "USES 仅允许 RESEARCH_QUESTION → METHOD；当前为 METHOD → CONCEPT。",
                },
              ],
            },
          },
          created_at: "2026-11-21T00:00:00Z",
          updated_at: "2026-11-21T00:00:00Z",
        },
      ]),
    );
    localStorage.setItem(
      "kb-fixture:localRecovery",
      JSON.stringify({
        version: "knowledge-local-recovery-1",
        available: true,
        preview_fingerprint: "reviewed-fingerprint",
        original_nodes: 19,
        original_edges: 20,
        kept_nodes: 19,
        kept_edges: 9,
        excluded_edges: [
          {
            index: 9,
            path: "graph.edges[9].type",
            code: "invalid_relation_types",
            relation_type: "USES",
            source_type: "METHOD",
            target_type: "CONCEPT",
            reason:
              "USES 仅允许 RESEARCH_QUESTION → METHOD；当前为 METHOD → CONCEPT。",
          },
        ],
      }),
    );
    localStorage.setItem(
      "kb-fixture:recoveryResult",
      JSON.stringify({
        version_id: "version-recovered",
        library_paper_id: "library-A",
        status: "partial",
        local_recovery: {
          version: "knowledge-local-recovery-1",
          available: false,
          original_nodes: 19,
          original_edges: 20,
          kept_nodes: 19,
          kept_edges: 9,
          excluded_edges: [
            {
              index: 9,
              path: "graph.edges[9].type",
              code: "invalid_relation_types",
              relation_type: "USES",
              source_type: "METHOD",
              target_type: "CONCEPT",
              reason:
                "USES 仅允许 RESEARCH_QUESTION → METHOD；当前为 METHOD → CONCEPT。",
            },
          ],
          published_version_id: "version-recovered",
        },
      }),
    );
  });
  await page.goto("/e2e/knowledge.html");
  await page
    .getByRole("button", { name: "研究内容知识库", exact: true })
    .click();
  await page.getByText("最近知识任务").click();
  await expect(
    page.getByRole("button", { name: "查看任务记录与本机恢复" }),
  ).toBeVisible();
  await expect(page.getByText("USES · METHOD → CONCEPT")).toHaveCount(0);
  await page.getByRole("button", { name: "查看任务记录与本机恢复" }).click();
  await expect(page.getByText("全部项目任务")).toBeVisible();
  await expect(
    page.getByText("失败原因 · 字段结构", { exact: false }),
  ).toBeVisible();
  await page.getByText("诊断详情", { exact: true }).click();
  await expect(
    page.getByText(
      "USES 仅允许 RESEARCH_QUESTION → METHOD；当前为 METHOD → CONCEPT。",
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "预览本机恢复" }).click();

  const dialog = page.getByRole("dialog", { name: "本机恢复预览" });
  await expect(dialog).toBeVisible();
  const stats = dialog.locator(".knowledge-recovery-stats span");
  await expect(stats.nth(0)).toHaveText("原知识节点19");
  await expect(stats.nth(1)).toHaveText("保留节点19");
  await expect(stats.nth(3)).toHaveText("保留关系9");
  await expect(stats.nth(4)).toHaveText("隔离关系1");
  await expect(dialog.getByText("USES · METHOD → CONCEPT")).toBeVisible();
  await expect(dialog.getByText(/当前为 METHOD → CONCEPT/)).toBeVisible();
  await expect(dialog.getByText(/不发送模型请求/)).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "确认保存为部分知识" }),
  ).toBeEnabled();
  expect(
    await page.evaluate(() => window.__knowledgeLocalRecoveryCalls),
  ).toEqual([{ action: "preview", runId: "failed-recovery-run" }]);
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);

  await page.setViewportSize({ width: 390, height: 850 });
  expect(
    await dialog.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
  ).toBe(true);
  await dialog.getByRole("button", { name: "确认保存为部分知识" }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("status")).toContainText("已保存为部分知识");
  await expect(page.getByRole("status")).toContainText("未调用模型");
  const recoveryCalls = await page.evaluate(
    () =>
      window.__knowledgeLocalRecoveryCalls as {
        action: string;
        runId: string;
        previewFingerprint?: string;
      }[],
  );
  expect(recoveryCalls.filter((call) => call.action === "recover")).toEqual([
    {
      action: "recover",
      runId: "failed-recovery-run",
      previewFingerprint: "reviewed-fingerprint",
    },
  ]);
  expect(
    recoveryCalls.filter((call) => call.action === "preview").length,
  ).toBeGreaterThanOrEqual(1);
  expect(await page.evaluate(() => window.__knowledgeModelCalls)).toEqual([]);
  expect(await page.evaluate(() => window.__knowledgeJobActions)).toEqual([]);
  expect(errors).toEqual([]);
});
