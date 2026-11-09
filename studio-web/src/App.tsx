import DraftReview from "./components/DraftReview";
import SettingsPanel from "./components/SettingsPanel";
import { Field, SectionTitle } from "./components/studio-ui";
import { statusNames, shouldPoll } from "./status";
import { useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  ArrowRight,
  Film,
  Image,
  Settings2,
  History,
  Plus,
  Check,
  Camera,
  Smartphone,
  UserRound,
  Globe,
  RefreshCw,
} from "lucide-react";
import Button from "./components/smoothui/smooth-button";
import Input from "./components/smoothui/animated-input";
import Tabs from "./components/smoothui/animated-tabs";
import FileUpload from "./components/smoothui/animated-file-upload";
import {
  api,
  post,
  upload,
  type Asset,
  type Job,
  type Role,
  type Settings,
  type SceneResults,
  type Language,
  type LanguageCheck,
  languages,
} from "./api";

const roleNames = { character: "人物", scene: "场景", game: "游戏画面" };
export default function App() {
  const [tab, setTab] = useState("create"),
    [assets, setAssets] = useState<Asset[]>([]),
    [jobs, setJobs] = useState<Job[]>([]),
    [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(""),
    [loaded, setLoaded] = useState(false);
  const lock = useRef(false),
    pollLock = useRef(false);
  const [theme, setTheme] = useState(""),
    [dialogue, setDialogue] = useState(""),
    [language, setLanguage] = useState<Language>("pt-BR"),
    [count, setCount] = useState(1),
    [mode, setMode] = useState("upload"),
    [selected, setSelected] = useState<Partial<Record<Role, string>>>({}),
    [scenePool, setScenePool] = useState<string[]>([]),
    [active, setActive] = useState<string | null>(null);
  const [checkResult, setCheckResult] = useState<LanguageCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const checkVersion = useRef(0);
  const sceneVersion = useRef(0);
  const checkCache = useRef<{key: string; result: LanguageCheck} | null>(null);
  const checkPending = useRef<{key: string; promise: Promise<LanguageCheck>} | null>(null);
  const dialogueLines = () => dialogue.split(/\r?\n/).filter((line) => line.trim().length > 0);
  function invalidateCheck() { checkVersion.current++; checkCache.current = null; setCheckResult(null); setChecking(false); }
  async function checkLanguage(lines: string[], selectedLanguage: Language): Promise<LanguageCheck> {
    if (!lines.length) return {status: "ok", results: []};
    const key = JSON.stringify([selectedLanguage, lines]);
    const version = checkVersion.current;
    if (checkCache.current?.key === key) return checkCache.current.result;
    setChecking(true);
    const promise = checkPending.current?.key === key ? checkPending.current.promise : post<LanguageCheck>("/language-check", {language: selectedLanguage, dialogue_lines: lines}).catch(() => ({status: "failed" as const, results: [], message: "语言检查失败，无法判断台词语言；可保留原文继续。"}));
    checkPending.current = {key, promise};
    const result = await promise;
    if (checkVersion.current === version) { checkCache.current = {key, result}; setCheckResult(result); setChecking(false); }
    if (checkPending.current?.promise === promise) checkPending.current = null;
    return result;
  }
  const [sceneMode, setSceneMode] = useState("upload"),
    [query, setQuery] = useState(""),
    [scenes, setScenes] = useState<SceneResults | null>(null);
  const current = jobs.find((j) => j.id === active);
  const batchJobs = current?.request.batch_id
    ? jobs
        .filter((job) => job.request.batch_id === current.request.batch_id)
        .sort((a, b) => (a.request.variation_index ?? 0) - (b.request.variation_index ?? 0))
    : current
      ? [current]
      : [];
  const character =
    mode === "default"
      ? assets.find((a) => a.role === "character" && a.is_default)
      : assets.find((a) => a.id === selected.character);
  const references = {
    character,
    scene: assets.find((a) => a.id === (sceneMode === "library" ? scenePool[0] : selected.scene)),
    game: assets.find((a) => a.id === selected.game),
  };
  const videoService = !settings
    ? "视频服务未配置"
    : settings.video_provider === "wavespeed"
      ? "WaveSpeed · Seedance 2.0 Mini · 480p"
      : settings.video_provider === "flova"
        ? "Flova · Seedance 2.5 · 720p"
        : `Seedance Ark · ${settings.ark_model}`;
  const mergeJob = (job: Job) =>
    setJobs((prev) => [job, ...prev.filter((j) => j.id !== job.id)]);
  const mergeJobs = (incoming: Job[]) =>
    setJobs((prev) => [...incoming, ...prev.filter((job) => !incoming.some((item) => item.id === job.id))]);
  async function act(key: string, fn: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true;
    setBusy(key);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "请求未完成，请重试。");
    } finally {
      lock.current = false;
      setBusy("");
    }
  }
  async function load() {
    await act("load", async () => {
      const [a, j, s] = await Promise.all([
        api<Asset[]>("/assets"),
        api<Job[]>("/jobs"),
        api<Settings>("/settings"),
      ]);
      setAssets(a);
      setJobs(j);
      setSettings(s);
      setLoaded(true);
    });
  }
  useEffect(() => {
    void load();
  }, []);
  useEffect(() => {
    if (!jobs.some(shouldPoll)) return;
    let cancelled = false;
    const timer = setInterval(async () => {
      if (pollLock.current || lock.current) return;
      pollLock.current = true;
      try {
        for (const job of jobs.filter(
          (j) =>
            ["queued", "running"].includes(j.status) ||
            (j.status === "submission_unknown" && !!j.task_id),
        )) {
          await post<Job>(`/jobs/${job.id}/refresh`);
        }
        const next = await api<Job[]>("/jobs");
        if (!cancelled) setJobs(next);
      } catch (e) {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "刷新失败，请重试。");
      } finally {
        pollLock.current = false;
      }
    }, 10000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [jobs]);
  function assetUpload(role: Role, files: File[]) {
    if (!files.length) {
      setSelected((s) => ({ ...s, [role]: undefined }));
      return;
    }
    void act(`upload-${role}`, async () => {
      const asset = await upload(files[0], role);
      setAssets((a) => [asset, ...a.filter((x) => x.id !== asset.id)]);
      setSelected((s) => ({ ...s, [role]: asset.id }));
    });
  }
  function uploadPanel(role: Role) {
    return (
      <div className="upload-wrap">
        <FileUpload
          key={`${role}-${selected[role] ?? "empty"}`}
          accept="image/png,image/jpeg,image/webp"
          multiple={false}
          maxSize={10 * 1024 * 1024}
          disabled={!!busy}
          onFilesSelected={(files) => assetUpload(role, files)}
        />
        {references[role] && (
          <div className="selected-asset">
            <img src={references[role]!.url} alt={`${roleNames[role]}参考图`} />
            <div>
              <strong>{references[role]!.name}</strong>
              <small>
                {references[role]!.width} × {references[role]!.height} · 已保存
              </small>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelected((s) => ({ ...s, [role]: undefined }))}
              disabled={!!busy}
            >
              移除
            </Button>
          </div>
        )}
        {busy === `upload-${role}` && <p role="status">正在保存图片…</p>}
      </div>
    );
  }
  function builtinLibrary(role: "character" | "scene") {
    const bundled = assets.filter((asset) =>
      asset.role === role && asset.source_url?.startsWith(`builtin://${role}/`),
    );
    const chosen = (id: string) => role === "scene" ? scenePool.slice(0, count).includes(id) : selected.character === id;
    return (
      <div className="builtin-library">
        <p>内置{roleNames[role]} · {bundled.length} 张。{role === "scene" && count > 1 ? `本批已选 ${Math.min(scenePool.length, count)} / ${count} 张，按选择顺序轮换。` : "点击选择本次参考。"}生成草稿时才会发送选中图片给导演模型。</p>
        {bundled.length ? (
          <div className="builtin-grid">
            {bundled.map((asset) => (
              <Button
                key={asset.id}
                variant="ghost"
                className={`builtin-card ${chosen(asset.id) ? "is-selected" : ""}`}
                aria-label={`选择${roleNames[role]} ${asset.name}`}
                aria-pressed={chosen(asset.id)}
                disabled={!!busy}
                onClick={() => {
                  if (role === "scene") {
                    setScenePool((old) => count === 1 ? [asset.id]
                      : old.includes(asset.id) ? old.filter((id) => id !== asset.id)
                      : old.length >= count ? old : [...old, asset.id]);
                  } else {
                    setSelected((old) => ({ ...old, character: asset.id }));
                  }
                }}
              >
                <img src={asset.url} alt="" loading="lazy" />
                <span>{asset.name}</span>
                {chosen(asset.id) && <Check size={15} aria-hidden="true" />}
              </Button>
            ))}
          </div>
        ) : (
          <p className="empty-small">还没有内置{roleNames[role]}。请使用上传入口。</p>
        )}
      </div>
    );
  }
  async function draft() {
    await act("draft", async () => {
      if (!theme.trim()) throw new Error("先填写这支视频的主题。");
      if (!character) throw new Error("请选择一张人物图片，或先设置默认人物。");
      if (!references.scene) throw new Error("请选择场景参考图。");
      const lines = dialogueLines();
      if (lines.length && lines.length !== count)
        throw new Error(`当前是 ${count} 条视频，请每条台词一行，共填 ${count} 行；或全部留空由导演创作。`);
      const version = checkVersion.current;
      const key = JSON.stringify([language, lines]);
      const wasVisible = checkCache.current?.key === key;
      const checked = await checkLanguage(lines, language);
      if (version !== checkVersion.current) throw new Error("台词或市场已修改，请重新生成草稿。");
      if (lines.length && !wasVisible && (checked.status === "failed" || checked.results.some((item) => item.status !== "match"))) {
        setNotice("请查看台词语言提示；确认保留原文后再次点击生成草稿。 ");
        return;
      }
      const warnings = lines.length ? lines.map((_, index) => {
        if (checked.status === "failed") return checked.message ?? "语言检查失败，无法判断台词语言。";
        const result = checked.results.find((item) => item.line === index + 1);
        return result && result.status !== "match" ? result.message : "";
      }) : [];
      const created = await post<Job[]>("/drafts/batch", {
        theme: theme.trim(),
        count,
        character_mode: mode === "default" ? "default" : "upload",
        character_ids: mode === "default" ? [] : [character.id],
        scene_ids: sceneMode === "library" ? scenePool.slice(0, count) : [references.scene.id],
        game_ids: references.game ? [references.game.id] : [],
        language,
        dialogue_lines: lines,
        language_warnings: warnings,
      });
      mergeJobs(created);
      setActive(created[0].id);
    });
  }
  return (
    <>
      <header className="topbar">
        <a
          href="#"
          className="logo"
          aria-label="videoX 首页"
          onClick={(e) => {
            e.preventDefault();
            setTab("create");
          }}
        >
          video<span>X</span>
          <span className="brand-divider" />
          <small>多市场 UGC 工作室</small>
        </a>
        <Tabs
          activeTab={tab}
          onChange={setTab}
          variant="pill"
          tabs={[
            { id: "create", label: "创作", icon: <Plus size={16} /> },
            { id: "jobs", label: "作品与任务", icon: <History size={16} /> },
            { id: "settings", label: "设置", icon: <Settings2 size={16} /> },
          ]}
        />
        <span className="local-badge">
          <span />
          本地工作空间
        </span>
      </header>
      <main>
        <section className="page-heading">
          <div>
            <div className="eyebrow">
              VIDEOX STUDIO <span>/</span> BRAZIL
            </div>
            <h1>
              {tab === "create"
                ? "让真实感，发生。"
                : tab === "jobs"
                  ? "每一次创作，都在这里。"
                  : "准备好你的工作室。"}
            </h1>
            <p>
              {tab === "create"
                ? "一个人物，一个场景。把你的想法变成 15 秒多市场 UGC。"
                : tab === "jobs"
                  ? "查看草稿、跟踪生成状态，找回保存在本地的视频。"
                  : "连接导演模型、视频服务与授权 Pinterest Board。"}
            </p>
          </div>
          <div className="heading-aside">
            <span className="accent-badge">pt-BR</span>
            <span>
              为竖屏而生
              <br />
              从灵感到一镜到底
            </span>
          </div>
        </section>
        {error && (
          <div className="message" role="alert">
            <div>
              <strong>这一步还没有完成</strong>
              <p>{error}</p>
            </div>
            <Button
              variant="soft"
              onClick={() => void load()}
              disabled={!!busy}
            >
              <RefreshCw size={15} />
              重新连接
            </Button>
          </div>
        )}
        {notice && (
          <div className="message" role="status">
            {notice}
          </div>
        )}
        {tab === "create" && (
          <div className="workspace">
            <div className="create-column">
              <section className="card create-card">
                <div className="card-top">
                  <span className="eyebrow">NEW CREATION</span>
                  <span className="tag">01 / 创意输入</span>
                </div>
                <SectionTitle
                  number="01"
                  title="这次，想说什么？"
                  detail="描述产品亮点、使用感受或开场想法，导演会组织所选语言口播。"
                />
                <Field>
                  <Input
                    label="视频主题"
                    placeholder="例如：午后咖啡时，分享刚发现的手机小游戏"
                    value={theme}
                    onChange={setTheme}
                  />
                </Field>
                <SectionTitle
                  number="02"
                  title="让主角进入场景"
                  detail="只需一张人物图。人物与环境分别参考，保持角色清晰。"
                />
                <div className="two-columns">
                  <div>
                    <div className="control-heading">
                      <UserRound size={16} />
                      <h3>人物参考</h3>
                      <span className="tag">必选</span>
                    </div>
                    <Tabs
                      variant="segment"
                      activeTab={mode}
                      onChange={setMode}
                      tabs={[
                        { id: "upload", label: "上传人物" },
                        { id: "library", label: "内置人物" },
                        { id: "default", label: "默认人物" },
                      ]}
                    />
                    {mode === "upload" ? (
                      uploadPanel("character")
                    ) : mode === "library" ? (
                      builtinLibrary("character")
                    ) : (
                      <div className="default-library">
                        {assets.filter((a) => a.role === "character").length ? (
                          assets
                            .filter((a) => a.role === "character")
                            .map((a) => (
                              <div className="selected-asset" key={a.id}>
                                <img src={a.url} alt={a.name} />
                                <div>
                                  <strong>{a.name}</strong>
                                  <Button
                                    size="sm"
                                    variant={a.is_default ? "soft" : "ghost"}
                                    disabled={!!busy || a.is_default}
                                    onClick={() =>
                                      void act("default", async () => {
                                        await post(`/assets/${a.id}/default`);
                                        setAssets(
                                          await api<Asset[]>("/assets"),
                                        );
                                      })
                                    }
                                  >
                                    {a.is_default ? "当前默认" : "设为默认"}
                                  </Button>
                                </div>
                              </div>
                            ))
                        ) : (
                          <p className="empty-small">
                            还没有人物。先上传一张，再存为默认人物。
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                  <div>
                    <div className="control-heading">
                      <Image size={16} />
                      <h3>场景参考</h3>
                      <span className="tag">必选</span>
                    </div>
                    <Tabs
                      variant="segment"
                      activeTab={sceneMode}
                      onChange={setSceneMode}
                      tabs={[
                        { id: "upload", label: "上传场景" },
                        { id: "library", label: "内置场景" },
                        { id: "pinterest", label: "Pinterest" },
                      ]}
                    />
                    {sceneMode === "upload" ? (
                      uploadPanel("scene")
                    ) : sceneMode === "library" ? (
                      builtinLibrary("scene")
                    ) : (
                      <div className="pinterest">
                        <p>搜索已授权 Board 中的图片</p>
                        <Input
                          label="场景关键词（可选，默认使用视频主题）"
                          value={query}
                          onChange={setQuery}
                        />
                        <Button
                          variant="soft"
                          disabled={!!busy || (!query.trim() && !theme.trim())}
                          loading={busy === "search"}
                          onClick={() =>
                            void act("search", async () => {
                              const version = sceneVersion.current;
                              const result = await post<SceneResults>("/scenes/search", {query: query.trim() || theme.trim(), language});
                              if (sceneVersion.current === version) setScenes(result);
                            })
                          }
                        >
                          查找场景 <ArrowUpRight size={14} />
                        </Button>
                        {scenes && (
                          <>
                            {scenes.recommended_query && (
                              <p>建议搜索：{scenes.recommended_query}</p>
                            )}
                            <a
                              href={scenes.search_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              在 Pinterest 搜索 ↗
                            </a>
                            {scenes.items.length === 0 && (
                              <p>
                                授权 Board
                                中没有匹配图片。可更换关键词或上传场景。
                              </p>
                            )}
                            <div className="candidates">
                              {scenes.items.map((pin) => (
                                <Button
                                  key={pin.id}
                                  variant="ghost"
                                  className="candidate"
                                  disabled={!!busy}
                                  onClick={() =>
                                    void act("import", async () => {
                                      const a = await post<Asset>(
                                        "/scenes/import",
                                        { pin_id: pin.id },
                                      );
                                      setAssets((old) => [
                                        a,
                                        ...old.filter((x) => x.id !== a.id),
                                      ]);
                                      setSelected((s) => ({
                                        ...s,
                                        scene: a.id,
                                      }));
                                    })
                                  }
                                >
                                  <img src={pin.image_url} alt={pin.title} />
                                  <span>{pin.title || "场景参考"}</span>
                                </Button>
                              ))}
                            </div>
                            {scenes.bookmark && (
                              <Button
                                variant="ghost"
                                disabled={!!busy}
                                onClick={() =>
                                  void act("search", async () => {
                                    const version = sceneVersion.current;
                                    const next = await post<SceneResults>(
                                      "/scenes/search",
                                      {
                                        query: query.trim() || theme.trim(),
                                  language,
                                        bookmark: scenes.bookmark,
                                      },
                                    );
                                    if (sceneVersion.current === version) setScenes({
                                      ...next,
                                      items: [...scenes.items, ...next.items],
                                    });
                                  })
                                }
                              >
                                更多候选
                              </Button>
                            )}
                          </>
                        )}
                        {references.scene && (
                          <p>
                            <Check size={14} />
                            已选择：{references.scene.name}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                </div>
                <div className="optional-panel">
                  <div>
                    <div className="control-heading">
                      <Smartphone size={16} />
                      <h3>游戏画面</h3>
                      <span className="tag">可选</span>
                    </div>
                    <p>上传后，它将是手机屏幕唯一允许出现的内容。</p>
                  </div>
                  {uploadPanel("game")}
                </div>
                <Field>
                  <label htmlFor="generation-count">生成数量（1–10条）</label>
                  <input id="generation-count" type="number" min={1} max={10} value={count}
                    onChange={(event) => {
                      const next = Math.max(1, Math.min(10, Number(event.target.value) || 1));
                      setCount(next);
                      setScenePool((old) => old.slice(0, next));
                    }} />
                  <small>每条会生成独立的钩子、人物动作、运镜路径、环境触发和台词。WaveSpeed 480p / 15秒当前参考价约 ${(count * 0.9).toFixed(2)} 美元/批。</small>
                </Field>
                <Field>
                  <label htmlFor="market-language">市场 / 口播语言</label>
                  <select id="market-language" value={language} onChange={(event) => { invalidateCheck(); sceneVersion.current++; setLanguage(event.target.value as Language); setScenes(null); }}>
                    <option value="pt-BR">巴西 · 巴西葡语</option><option value="es-MX">墨西哥 · 墨西哥西班牙语</option><option value="en-US">美国 · 美式英语</option><option value="fil-PH">菲律宾 · Filipino（菲律宾语）</option>
                  </select>
                </Field>
                <Field>
                  <label htmlFor="dialogue-lines">{languages[language]}台词（可选）</label>
                  <textarea id="dialogue-lines" rows={Math.min(10, Math.max(3, count))}
                    placeholder={count === 1 ? "留空由导演创作，或填写一条台词" : `留空由导演创作 ${count} 条，或每条视频填一行（共 ${count} 行）`}
                    value={dialogue} aria-describedby="dialogue-help dialogue-check" onChange={(event) => { invalidateCheck(); setDialogue(event.target.value); }} onBlur={() => void checkLanguage(dialogueLines(), language)} />
                  <small id="dialogue-help">填写时逐行原样保留；留空时由导演创作。语言检查会额外调用已配置的导演模型，可能产生少量费用。</small>
                  <div id="dialogue-check" role="status" aria-live="polite">
                    {checking && <p>正在检查台词语言…</p>}
                    {checkResult?.status === "failed" && <><p>{checkResult.message}</p><Button type="button" variant="ghost" disabled={checking} onClick={() => { checkCache.current = null; void checkLanguage(dialogueLines(), language); }}>重新检查台词语言</Button></>}
                    {checkResult?.status === "ok" && checkResult.results.filter((item) => item.status !== "match").map((item) => <p key={item.line}>{item.message}</p>)}
                    {checkResult?.status === "ok" && checkResult.results.length > 0 && checkResult.results.every((item) => item.status === "match") && <p>台词语言检查完成。</p>}
                    {checkResult && <small>提示仅供参考，可以保留原文继续。</small>}
                  </div>
                </Field>
                <div className="submit-row">
                  <p>
                    <span className="tiny-dot" />
                    先生成导演草稿，审核后再提交视频。
                  </p>
                  <Button
                    className="primary-cta"
                    onClick={() => void draft()}
                    loading={busy === "draft"}
                    disabled={!!busy || !loaded}
                  >
                    生成导演草稿（{count} 条） <ArrowRight size={17} />
                  </Button>
                </div>
              </section>
              {current && (
                <>
                  {batchJobs.length > 1 && (
                    <section className="card batch-review-card" aria-label="本批导演草稿">
                      <div className="card-top">
                        <div>
                          <span className="eyebrow">BATCH REVIEW</span>
                          <h2>本批 {batchJobs.length} 条导演草稿</h2>
                        </div>
                        <span className="tag">约 ${(batchJobs.length * 0.9).toFixed(2)} 美元</span>
                      </div>
                      <div className="batch-draft-tabs">
                        {batchJobs.map((job) => (
                          <Button
                            key={job.id}
                            size="sm"
                            variant={job.id === current.id ? "soft" : "ghost"}
                            onClick={() => setActive(job.id)}
                          >
                            {String(job.request.variation_index ?? 1).padStart(2, "0")} · {statusNames[job.status] ?? job.status}
                          </Button>
                        ))}
                      </div>
                      <div className="submit-row">
                        <p>请逐条切换检查台词、动作、运镜和场景；此按钮将授权整批付费提交。</p>
                        <Button
                          disabled={!!busy || batchJobs.some((job) => job.status !== "draft_ready")}
                          loading={busy === "generate-batch"}
                          onClick={() =>
                            void act("generate-batch", async () => {
                              const submitted = await post<Job[]>("/jobs/generate-batch", {
                                job_ids: batchJobs.map((job) => job.id),
                              });
                              mergeJobs(submitted);
                              setNotice(`本批 ${submitted.length} 条已进入提交队列。`);
                            })
                          }
                        >
                          确认并提交本批 {batchJobs.length} 条视频 <ArrowUpRight size={16} />
                        </Button>
                      </div>
                    </section>
                  )}
                  <DraftReview
                    assets={assets}
                    model={videoService}
                    job={current}
                    busy={!!busy}
                    onGenerate={() =>
                      void act("generate", async () =>
                        mergeJob(await post<Job>(`/jobs/${current.id}/generate`)),
                      )
                    }
                  />
                </>
              )}
            </div>
            <aside className="summary">
              <section className="card summary-card">
                <div className="card-top">
                  <span className="eyebrow">PRODUCTION NOTES</span>
                  <Camera size={18} />
                </div>
                <h2>一镜，十五秒。</h2>
                <p>完整的动作链，自然发生的对白。</p>
                <div className="specs">
                  <div>
                    <strong>
                      15<span>s</span>
                    </strong>
                    <small>固定时长</small>
                  </div>
                  <div>
                    <strong>9:16</strong>
                    <small>竖屏画幅</small>
                  </div>
                  <div>
                    <strong>1</strong>
                    <small>连续镜头</small>
                  </div>
                </div>
                <div className="reference-grid">
                  {(["character", "scene", "game"] as Role[]).map((role) => (
                    <div key={role}>
                      <div className="reference-preview">
                        {references[role] ? (
                          <img
                            src={references[role]!.url}
                            alt={roleNames[role] + "预览"}
                          />
                        ) : role === "character" ? (
                          <UserRound />
                        ) : role === "scene" ? (
                          <Image />
                        ) : (
                          <Smartphone />
                        )}
                      </div>
                      <small>
                        {roleNames[role]}{" "}
                        {references[role]
                          ? "✓"
                          : role === "game"
                            ? "· 可选"
                            : "· 待选"}
                      </small>
                    </div>
                  ))}
                </div>
                <div className="notes">
                  <div>
                    <UserRound />
                    <p>
                      <strong>一个确定的主角</strong>
                      <span>人物图锁定身份，不新增其他人物。</span>
                    </p>
                  </div>
                  <div>
                    <Globe />
                    <p>
                      <strong>会呼吸的环境</strong>
                      <span>场景带动环境声、背景运动和取景变化。</span>
                    </p>
                  </div>
                  <div>
                    <Smartphone />
                    <p>
                      <strong>让展示动作成立</strong>
                      <span>
                        手机首帧就在场，接触、拿起，再稳定展示约 4 秒。
                      </span>
                    </p>
                  </div>
                </div>
              </section>
              <div className="review-note">
                <span>导演手记 / 001</span>
                <p>
                  好的 UGC，不像在表演。
                  <br />
                  像生活里刚好发生的一刻。
                </p>
                <small>
                  生成后请检查人物一致性、口播与屏幕内容。参考约束不等于逐像素保证。
                </small>
              </div>
            </aside>
          </div>
        )}
        {tab === "jobs" && (
          <section className="card history-card">
            <div className="card-top">
              <h2>
                作品与任务 <span className="tag">{jobs.length}</span>
              </h2>
              <Button
                variant="soft"
                disabled={!!busy}
                onClick={() => void load()}
              >
                <RefreshCw size={15} />
                刷新
              </Button>
            </div>
            {jobs.length === 0 ? (
              <div className="empty-state">
                <Film size={38} />
                <h2>第一支作品，从一个想法开始。</h2>
                <p>还没有任务。生成导演草稿后，它会自动保存在这里。</p>
                <Button onClick={() => setTab("create")}>
                  开始创作 <ArrowRight size={16} />
                </Button>
              </div>
            ) : (
              jobs.map((job) => (
                <article className="job-entry" key={job.id}>
                  <div className="job-heading">
                    <div>
                      <small>
                        {new Date(job.created_at).toLocaleString("zh-CN")}
                      </small>
                      <h3>{job.theme}</h3>
                      <small>任务语言：{languages[job.request.language ?? "pt-BR"]}</small>
                    </div>
                    <span className="tag">
                      {statusNames[job.status] ?? job.status}
                    </span>
                    <Button
                      variant="soft"
                      onClick={() =>
                        setActive(active === job.id ? null : job.id)
                      }
                    >
                      查看详情
                    </Button>
                  </div>
                  {active === job.id && (
                    <DraftReview
                      assets={assets}
                      model={videoService}
                      job={job}
                      busy={!!busy}
                      onGenerate={() =>
                        void act("generate", async () =>
                          mergeJob(await post<Job>(`/jobs/${job.id}/generate`)),
                        )
                      }
                    />
                  )}
                </article>
              ))
            )}
          </section>
        )}
        {tab === "settings" &&
          (settings ? (
            <SettingsPanel
              settings={settings}
              busy={!!busy}
              onSave={(values) =>
                void act("settings", async () => {
                  const result = await api<Settings>("/settings", {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(values),
                  });
                  setSettings(result);
                  setNotice("设置已保存。密钥不会保存在浏览器中。");
                })
              }
            />
          ) : (
            <section className="card empty-state">
              <h2>尚未连接本地服务</h2>
              <Button disabled={!!busy} onClick={() => void load()}>
                重新连接
              </Button>
            </section>
          ))}
      </main>
      <footer>
        <span>Robin X · 设计工程师</span>
        <span>以设计定义体验，以工程成就创作。</span>
      </footer>
    </>
  );
}
