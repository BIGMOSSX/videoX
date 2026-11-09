import { useState } from "react";
import { ArrowUpRight, Camera, AudioLines, LoaderCircle } from "lucide-react";
import { languages, type Asset, type Job } from "../api";
import { statusNames, shouldPoll } from "../status";
import Button from "./smoothui/smooth-button";
export default function DraftReview({
  job,
  busy,
  onGenerate,
  model,
  assets,
}: {
  job: Job;
  busy: boolean;
  onGenerate: () => void;
  model: string;
  assets: Asset[];
}) {
  const [showPrompt, setShowPrompt] = useState(false);
  return (
    <section className="card draft-card">
      <div className="card-top">
        <span className="eyebrow">DIRECTOR’S DRAFT</span>
        <span className="tag">{statusNames[job.status] ?? job.status}</span>
      </div>
      <h2>{job.draft?.title ?? "导演正在组织这段故事"}</h2>
      <p>任务语言：{languages[job.request.language ?? "pt-BR"]}</p>
      {job.request.language_warning && <p className="message" role="note">{job.request.language_warning}</p>}
      <div className="reference-grid" aria-label="本任务参考图片">
        {([['character_id', '人物'], ['scene_id', '场景'], ['game_id', '游戏']] as const).map(([field, label]) => {
          const id = job.request[field];
          const asset = assets.find((item) => item.id === id);
          return <div key={field}>
            <div className="reference-preview">
              {asset ? <img src={asset.url} alt={`本任务${label}参考：${asset.name}`} /> : <small>{id ? '参考图片不可用' : '未指定'}</small>}
            </div>
            <small>{label} · {asset?.name ?? id ?? '未指定'}</small>
          </div>;
        })}
      </div>
      {job.error && (
        <p className="message" role="alert">
          {job.error}
        </p>
      )}
      {shouldPoll(job) && (
        <p className="progress-state" role="status">
          <LoaderCircle className="animate-spin" size={16} />{" "}
          {statusNames[job.status]} · 状态每 10 秒更新
        </p>
      )}
      {job.status === "submission_unknown" && (
        <p>
          服务商提交结果尚不确定。请核对服务商任务记录，避免重复付费；本任务不会自动重新提交。
        </p>
      )}
      {job.draft && (
        <>
          <div className="dialogue">
            <small>口播 / {languages[job.request.language ?? "pt-BR"]}</small>
            <p lang={job.request.language ?? "pt-BR"}>{job.draft.dialogue ?? job.draft.dialogue_pt_br}</p>
          </div>
          <div className="scene-directions">
            {job.draft.hook && <p><strong>开场钩子</strong>{job.draft.hook}</p>}
            <p>
              <strong>场景</strong>
              {job.draft.scene_description}
            </p>
            <p>
              <strong>背景运动</strong>
              {job.draft.background_motion}
            </p>
            <p>
              <strong>环境声音</strong>
              {job.draft.ambience}
            </p>
          </div>
          <h3>连续镜头内的四个节拍</h3>
          <div className="beats">
            {job.draft.beats.map((beat, i) => (
              <div className="beat" key={beat.start}>
                <div className="beat-time">
                  <span>{String(i + 1).padStart(2, "0")}</span>
                  <strong>
                    {beat.start}–{beat.end}s
                  </strong>
                </div>
                <p>{beat.action}</p>
                <small>
                  <Camera size={14} />
                  {beat.camera}
                </small>
                <small>
                  <AudioLines size={14} />
                  {beat.audio}
                </small>
              </div>
            ))}
          </div>
          <Button
            variant="ghost"
            onClick={() => setShowPrompt(!showPrompt)}
            aria-expanded={showPrompt}
          >
            {showPrompt ? "收起" : "展开"}完整生成提示词
          </Button>
          {showPrompt && (
            <pre className="prompt">{job.prompt ?? "提示词尚未就绪"}</pre>
          )}
          <div className="submit-row">
            <a
              href={`/api/jobs/${job.id}/packet`}
              target="_blank"
              rel="noreferrer"
            >
              导出提示词与参考映射 ↗
            </a>
            {job.status === "draft_ready" && (
              <div className="generate-action">
                <small>视频服务：{model}</small>
                <Button disabled={busy} onClick={onGenerate}>
                  确认草稿，提交视频 <ArrowUpRight size={16} />
                </Button>
              </div>
            )}
          </div>
        </>
      )}
      {job.video_url && (
        <div className="video-result">
          <video controls preload="metadata" src={job.video_url} />
          {job.review_status && (
            <div className="review-note" role="note">
              <span>成片人工检查</span>
              <p>{job.review_status}</p>
            </div>
          )}
          <a href={job.video_url} download>
            下载视频 ↗
          </a>
        </div>
      )}
    </section>
  );
}
