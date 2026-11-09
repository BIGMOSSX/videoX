import { useState, useEffect } from "react";
import { Check } from "lucide-react";
import type { Settings } from "../api";
import Button from "./smoothui/smooth-button";
import Input from "./smoothui/animated-input";
import Tabs from "./smoothui/animated-tabs";
import { Field, SectionTitle } from "./studio-ui";
export default function SettingsPanel({
  settings,
  busy,
  onSave,
}: {
  settings: Settings;
  busy: boolean;
  onSave: (values: Record<string, string>) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({
    llm_base_url: settings.llm_base_url,
    llm_model: settings.llm_model,
    video_provider: settings.video_provider,
    wavespeed_model: settings.wavespeed_model,
    wavespeed_resolution: settings.wavespeed_resolution,
    ark_model: settings.ark_model,
    flova_model: settings.flova_model,
    flova_resolution: settings.flova_resolution,
    flova_cli_path: settings.flova_cli_path,
    pinterest_board_id: settings.pinterest_board_id,
  });
  useEffect(() => {
    setValues({
      llm_base_url: settings.llm_base_url,
      llm_model: settings.llm_model,
      video_provider: settings.video_provider,
      wavespeed_model: settings.wavespeed_model,
      wavespeed_resolution: settings.wavespeed_resolution,
      ark_model: settings.ark_model,
      flova_model: settings.flova_model,
      flova_resolution: settings.flova_resolution,
      flova_cli_path: settings.flova_cli_path,
      pinterest_board_id: settings.pinterest_board_id,
    });
  }, [settings]);
  const field = (key: string, label: string, secret = false) => (
    <Field>
      <Input
        label={label}
        type={secret ? "password" : "text"}
        value={values[key] ?? ""}
        onChange={(value) => setValues((v) => ({ ...v, [key]: value }))}
      />
    </Field>
  );
  return (
    <form
      className="card settings-card"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(
          Object.fromEntries(
            Object.entries(values).filter(
              ([key, value]) =>
                ![
                  "llm_api_key",
                  "wavespeed_api_key",
                  "flova_api_key",
                  "ark_api_key",
                  "pinterest_access_token",
                ].includes(key) || value.trim(),
            ),
          ),
        );
      }}
    >
      <div className="card-top">
        <span className="eyebrow">CONNECTIONS</span>
        <span className="tag">密钥仅发往本地服务</span>
      </div>
      <SectionTitle
        number="01"
        title="DeepSeek 视觉导演"
        detail={`分析人物、场景和游戏截图并输出结构化多市场 UGC 草稿 · ${settings.configured.llm ? "已配置" : "未配置"}`}
      />
      {field("llm_base_url", "DeepSeek API 地址")}
      {field("llm_model", "视觉模型名称")}
      {field("llm_api_key", "DeepSeek API Key（留空保留）", true)}
      <SectionTitle
        number="02"
        title="视频生成"
        detail={`当前：${values.video_provider === "wavespeed" ? "WaveSpeed Seedance 2.0 Mini 480p" : values.video_provider === "flova" ? "Flova Seedance 2.5 720p" : "Seedance Ark"}`}
      />
      <Tabs
        variant="segment"
        activeTab={values.video_provider}
        onChange={(value) => setValues((current) => ({ ...current, video_provider: value }))}
        tabs={[
          { id: "wavespeed", label: "WaveSpeed" },
          { id: "ark", label: "火山方舟" },
          { id: "flova", label: "Flova（可选）" },
        ]}
      />
      {values.video_provider === "wavespeed" && <>
        <p className="provider-note">Seedance 2.0 Mini · 480p · 15秒 · 最多9张参考图。官方当前标价约 $0.90/条，提交前仍以 WaveSpeed 实时价格为准。</p>
        {field("wavespeed_api_key", "WaveSpeed API Key（留空保留）", true)}
      </>}
      {values.video_provider === "ark" && <>
        {field("ark_model", "Ark 模型 / Endpoint ID")}
        {field("ark_api_key", "Ark API 密钥（留空保留）", true)}
      </>}
      {values.video_provider === "flova" && <>
        <p className="provider-note">Flova 是项目型 Agent CLI，而不是单一 REST 视频端点；保留为备用流程。</p>
        {field("flova_cli_path", "Flova CLI 路径")}
        {field("flova_api_key", "Flova Agent API Key（留空保留）", true)}
      </>}
      <SectionTitle
        number="03"
        title="Pinterest 授权 Board"
        detail={`仅检索你已授权的 Board · ${settings.configured.pinterest ? "已配置" : "未配置"}`}
      />
      {field("pinterest_board_id", "Board ID")}
      {field(
        "pinterest_access_token",
        "Pinterest Access Token（留空保留）",
        true,
      )}
      <div className="submit-row">
        <p>凭据存储：{settings.credential_storage}</p>
        <Button type="submit" disabled={busy}>
          保存设置 <Check size={16} />
        </Button>
      </div>
    </form>
  );
}
