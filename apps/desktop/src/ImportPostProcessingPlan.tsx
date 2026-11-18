import { useId } from "react";
import type { PostImportPlan } from "./api";

export function ImportPostProcessingPlan({
  value,
  onChange,
}: {
  value: PostImportPlan;
  onChange: (next: PostImportPlan) => void;
}) {
  const translationGroup = useId();
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
          <strong>导入后生成</strong>
          <p className="muted">
            选择论文后直接按章节调用文档模型，导出正文、公式和表格。
          </p>
        </div>
        <span className="import-plan-badge">模型优先</span>
      </div>
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
            set({ modality: event.target.value as PostImportPlan["modality"] })
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
    </section>
  );
}
