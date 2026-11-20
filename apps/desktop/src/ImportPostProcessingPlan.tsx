import { useId } from "react";
import { useQuery } from "@tanstack/react-query";
import { request, type PostImportPlan } from "./api";
import type { GlobalModels } from "./ModelSettings";

export function ImportPostProcessingPlan({
  value,
  onChange,
}: {
  value: PostImportPlan;
  onChange: (next: PostImportPlan) => void;
}) {
  const translationGroup = useId();
  const batching = value.document_batching ?? true;
  const boundaryReview = value.allow_boundary_review ?? true;
  const formatRepair = value.allow_format_repair ?? false;
  const pagesPerBatch = value.pages_per_batch ?? 5;
  const models = useQuery({
    queryKey: ["import-model-settings"],
    queryFn: () => request<GlobalModels>("GET", "/api/v1/settings/models"),
    enabled: value.parse,
    retry: false,
  });
  const selected = models.data?.profiles?.find(
    (profile) => profile.id === models.data?.roles?.document_parse,
  );
  const capabilities = selected?.parameters.capabilities;
  const supportsPdf =
    capabilities?.document_input !== "text" &&
    !!capabilities?.document_input &&
    (capabilities.document_transport === "chat_file" ||
      (capabilities.document_transport === "chat_images" &&
        capabilities.document_input === "image" &&
        capabilities.multimodal === true));
  const set = (patch: Partial<PostImportPlan>) =>
    onChange({
      ...value,
      ...patch,
      parse: true,
      extract_formulas: true,
      extract_tables: true,
    });

  return (
    <section className="import-plan-card" aria-label="导入后处理计划">
      <div className="import-plan-heading">
        <div>
          <strong>解析方式</strong>
          <p className="muted">
            本地解析生成可检索的本地库；也可选择模型读取
            PDF，或导入后再进行模型解析。
          </p>
        </div>
        <span className="import-plan-badge">
          {value.parse ? "模型解析" : "本地解析"}
        </span>
      </div>
      <fieldset className="import-plan-fieldset">
        <legend>论文解析方式</legend>
        <label>
          <input
            type="radio"
            name={`parse-mode-${translationGroup}`}
            checked={!value.parse}
            onChange={() =>
              onChange({ ...value, parse: false, allow_network: false })
            }
          />
          本地解析（不调用模型）
        </label>
        <label>
          <input
            type="radio"
            name={`parse-mode-${translationGroup}`}
            checked={value.parse}
            onChange={() =>
              onChange({ ...value, parse: true, allow_network: false })
            }
          />
          模型解析 PDF
        </label>
      </fieldset>
      {!value.parse ? (
        <p className="muted">
          自动提取本地正文、章节和检索索引；失败可重试。公式和复杂表格可能不完整，可稍后在论文管理中改用模型解析。
        </p>
      ) : (
        <>
          <p role="status">
            {selected
              ? `论文解析模型：${selected.name} · ${selected.model}`
              : "尚未选择论文解析模型"}
          </p>
          {supportsPdf && (
            <p className="muted">
              {capabilities?.document_transport === "chat_images"
                ? "输入方式：将 PDF 页面渲染成图片，正文、公式和表格由视觉模型识别。"
                : "输入方式：直接发送 PDF 文件，需要端点支持文件输入。"}
              {` 单请求响应等待上限 ${selected?.parameters.document_timeout_seconds ?? 600} 秒，单请求总时限 ${selected?.parameters.document_total_timeout_seconds ?? 1800} 秒；不是整篇任务的总用时上限。`}
            </p>
          )}
          {(!supportsPdf || models.isError) && (
            <p className="import-plan-warning">
              请在“设置与诊断 → 模型”编辑提供商，声明该模型实际支持 PDF
              文件输入或视觉图片输入，并选择相应传输方式和“论文解析模型”。联网授权和文本连接测试不能赋予
              PDF 能力；不支持文件或图片的模型请使用本地解析。
            </p>
          )}
          <fieldset className="import-plan-fieldset">
            <legend>模型解析批次</legend>
            <label>
              <input
                type="checkbox"
                checked={batching}
                onChange={(event) =>
                  set({
                    document_batching: event.target.checked,
                    allow_network: false,
                  })
                }
              />
              按页分批解析（顺序执行）
            </label>
            {batching ? (
              <>
                <label className="import-plan-select">
                  每批最多页数（含共享页）
                  <select
                    value={pagesPerBatch}
                    onChange={(event) =>
                      set({
                        pages_per_batch: Number(event.target.value),
                        allow_network: false,
                      })
                    }
                  >
                    {[2, 3, 4, 5, 6, 7, 8].map((pages) => (
                      <option key={pages} value={pages}>
                        {pages} 页
                      </option>
                    ))}
                  </select>
                </label>
                <p className="muted">
                  相邻批次共享 1
                  页并保留原始页码；容量不足时只缩小批次。成功批次保存检查点，继续任务时不重新解析已成功批次。
                </p>
                <label>
                  <input
                    type="checkbox"
                    checked={boundaryReview}
                    onChange={(event) =>
                      set({
                        allow_boundary_review: event.target.checked,
                        allow_network: false,
                      })
                    }
                  />
                  允许按需调用模型检查相邻批次的截断与续接
                </label>
                <p className="muted">
                  每个相邻边界最多额外 1 次 API
                  请求，可能增加费用；不能确认的续接保留为未解决，不猜测合并。
                </p>
                <label>
                  <input
                    type="checkbox"
                    checked={formatRepair}
                    onChange={(event) =>
                      set({
                        allow_format_repair: event.target.checked,
                        allow_network: false,
                      })
                    }
                  />
                  允许契约校验失败时修复本批格式（可能额外收费）
                </label>
                <p className="muted">
                  默认关闭。每个失败批次最多额外 1 次 API
                  请求，仅发送该批响应、契约和错误，不重传
                  PDF；再次校验失败即停止，不循环重试。格式修复不保证内容准确。
                </p>
                <p className="muted" aria-label="解析请求预算">
                  若最终为 B 个批次：抽取 B 次
                  {boundaryReview ? "，边界检查最多 B−1 次" : "，边界检查 0 次"}
                  {formatRepair ? "，格式修复最多 B 次" : "，格式修复 0 次"}
                  。实际批次数准备文件后确定；概览、精读和翻译另计。
                </p>
              </>
            ) : (
              <p className="muted">
                一次发送完整
                PDF；本次不使用批次检查点、批次格式修复或相邻边界检查。
              </p>
            )}
          </fieldset>
          <div className="import-plan-options">
            <label>
              <input
                type="checkbox"
                checked={value.overview}
                onChange={(event) => set({ overview: event.target.checked })}
              />
              生成论文概览
            </label>
            <label>
              <input
                type="checkbox"
                checked={value.reading}
                onChange={(event) => set({ reading: event.target.checked })}
              />
              生成论文精读
            </label>
          </div>
          {value.reading && (
            <fieldset className="import-plan-fieldset">
              <legend>精读中文翻译</legend>
              <label>
                <input
                  type="radio"
                  name={`translation-mode-${translationGroup}`}
                  value="none"
                  checked={value.translation_mode === "none"}
                  onChange={() => set({ translation_mode: "none" })}
                />
                不生成逐段翻译（保留英文原文和中文论证批注）
              </label>
              <label>
                <input
                  type="radio"
                  name={`translation-mode-${translationGroup}`}
                  value="full"
                  checked={value.translation_mode === "full"}
                  onChange={() => set({ translation_mode: "full" })}
                />
                生成逐段中文翻译
              </label>
            </fieldset>
          )}
          <label className="import-plan-select">
            多模态策略
            <select
              value={value.modality}
              onChange={(event) =>
                set({
                  modality: event.target.value as PostImportPlan["modality"],
                })
              }
            >
              <option value="auto">
                自动降级：无多模态时跳过图片，保留公式/表格退化结果
              </option>
              <option value="required">需要多模态，否则暂停解析</option>
            </select>
          </label>
          <label className="import-plan-network">
            <input
              type="checkbox"
              checked={value.allow_network}
              onChange={(event) => set({ allow_network: event.target.checked })}
            />
            允许将所选 PDF 发送给已配置的论文解析模型
          </label>
          {batching && (
            <p className="muted">
              本次联网授权涵盖多次批次请求
              {boundaryReview ? "和按需边界检查" : ""}
              {formatRepair ? "及已勾选的格式修复" : ""}
              ，可能增加用量和费用；修改批次或修复选项后需重新勾选授权。
            </p>
          )}
          <div className="import-plan-materials" role="status">
            <span>✓ 公式：必须请求提取</span>
            <span>✓ 表格：必须请求提取</span>
            <span>图片：无多模态时可跳过</span>
          </div>
          {value.modality === "required" && (
            <p className="muted import-plan-warning">
              当前模型能力会在提交前检查；不支持视觉或 PDF
              文档输入时，任务会暂停，不会静默降级。
            </p>
          )}
          {!value.allow_network && (
            <p className="muted import-plan-warning">
              未授权联网时不会发送
              PDF；提交后会提示需要授权，避免意外产生模型请求或费用。
            </p>
          )}
        </>
      )}
    </section>
  );
}
