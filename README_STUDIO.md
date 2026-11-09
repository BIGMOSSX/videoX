# videoX 多市场 UGC 工作室

基于 videoX 的 Windows 本地网页面板。固定 **15秒 / 9:16 / 一镜到底**。单张人物图负责唯一角色，场景图负责环境，可选游戏图负责手机唯一指定画面。支持巴西葡语、墨西哥西班牙语、美式英语和 Filipino（菲律宾语），默认巴西葡语；市场选择不会替换参考素材。

## Windows 启动

1. 解压 ZIP，进入 `videoX` 文件夹，双击 **`一键启动.cmd`**。无需输入命令。已安装 Python 3.11+ 时会直接使用；未安装时会尝试通过 Windows `winget` 自动按用户范围安装 Python 3.11，随后自动安装工作室依赖。首次启动需要联网，可能需要几分钟；若系统没有 `winget`，窗口会用中文说明手动安装方法。
2. 启动器自动打开 `http://127.0.0.1:8787`。以后再次双击同一个文件即可；如果工作室已在运行，会直接打开网页。
3. 使用期间保留服务窗口。关闭网页不影响后台；关闭服务后已保存的远程任务 ID 会在下次启动时恢复查询。
4. ZIP 已包含构建好的网页，正常使用不需要 Node.js；从 Git 源码启动或修改前端后才需要 Node.js 22+。这仍是自动准备环境的本地网页程序，不是免依赖的 `.exe` 安装包。

仓库提供 `.github/workflows/windows-studio.yml`：在 GitHub Windows 云主机上检查 Python/前端测试、打包、解压后双击中文入口启动、网页健康检查与重复启动。云端流程不需要服务密钥，也不会付费生成视频；仓库不会上传本地内置真人照片。只有工作流实际运行且通过后，才能声称 Windows 云端验收完成。

## 配置真实服务

新安装的导演层默认使用 DeepSeek `deepseek-v4-flash-vision-exp`（`https://api.deepseek.com`），它会同时理解人物、场景和游戏图，然后生成所选语言的可审核台词、动作、运镜、动态背景和声音时间线。导演草稿不会自动跨过付费边界。

视频层默认使用 WaveSpeed `bytedance/seedance-2.0-mini/text-to-video`，固定 **480p / 9:16 / 15秒 / 原生声音**。按 WaveSpeed 当前公开价格，480p 约为 0.06 美元/秒，即每条 15 秒约 0.90 美元；最终以提交时服务商实时价格为准。应用不自动付费重试；提交结果不明时会停在“待确认”。

Windows 通过系统凭据管理器保存密钥，前端不读取已保存密钥。环境变量优先于设置页密钥。非 Windows 开发环境使用下列变量：

```text
STUDIO_LLM_BASE_URL
STUDIO_LLM_MODEL
STUDIO_LLM_API_KEY
WAVESPEED_API_KEY
WAVESPEED_VIDEO_MODEL       可选，默认为 Seedance 2.0 Mini 端点
WAVESPEED_VIDEO_RESOLUTION  可选，当前仅允许 480p
ARK_API_KEY
ARK_SEEDANCE_MODEL         可选
PINTEREST_ACCESS_TOKEN
PINTEREST_BOARD_ID
STUDIO_DATA_DIR            可选，默认仓库 .studio/
```

未配置时页面明确报告缺失项；不会生成虚假脚本或视频。2026-09-14 已使用 DeepSeek 视觉模型与 WaveSpeed Seedance 2.0 Mini 完成真实端到端验收；密钥未写入仓库或 Windows ZIP。

## 人物与场景

创作页现有“内置人物”和“内置场景”图库，分别包含本次提供的 26 张人物图、27 张场景图；点击缩略图即可选为本次参考。图片已转换为去除元数据的 WebP，并随 Windows ZIP 分发。另可上传 JPG/PNG/WebP（宽高 300–6000px，10MB以内），或在“默认人物”中设定长期复用的角色。图库选择本身不会向外部服务传图；点击生成导演草稿才会把选中的参考图发送到 DeepSeek，审核后确认视频生成才会发送到 WaveSpeed。默认角色在创建任务时即固定，之后修改默认角色不会影响既有任务。由于安装包实际包含真人照片，转发安装包、使用肖像进行 AI 视频或商用前，请确认每张照片的肖像权和使用授权。WaveSpeed 或底层模型仍可能因真人权利或安全规则拒绝素材。

Pinterest 使用官方 API 读取已授权 Board，需要相应 `boards:read`、`pins:read` 权限。Board 授权本身不代表素材版权授权；用于生成的 Board 应仅收录你有权商用和用于 AI 参考的图片。界面按关键词筛选 Board 候选，并提供 Pinterest 站内搜索链接；没有伪装成全站搜索 API，也不绕过登录或抓取限制。也可以直接选内置场景或上传自有场景图。

游戏图片可选。上传后，提示词明确它是手机唯一屏幕来源，禁止模型另造、重绘、替换界面；这是生成指令，不能保证模型逐像素服从。成片仍需检查人物、手指、背景连续性、目标语言的发音与口型和屏幕内容。未提供游戏图时不编造 UI。

## 工作流程与数据

输入主题 → 选择市场 → 上传/选择人物、场景、游戏图 → 选择 1–10 条 → 导演分别生成草稿 → 逐条检查台词、背景动作、声音和连续时间节拍 → 单条提交或整批确认付费 → 后台查询 → 本地播放/下载。批量模式可在“内置场景”中多选图片，任务按点选顺序轮换场景；只选一张时仍会复用同一场景，但钩子、动作和台词分别策划。整批提交会核对批次 ID、条数和序号，不会把不同批的草稿混在一起。

手动台词按非空行对应视频，原文保留，不自动翻译。语言检查使用已配置的导演模型，可能产生少量额外费用；它不发送图片，不提交视频。短句、品牌名和菲律宾语夹英语等内容可能无法可靠识别，检查失败或无法判断时仍可继续。每条任务保存自己的市场，旧任务缺少语言时按巴西葡语读取；切换表单不会改变历史任务。模拟测试只能验证数据和提示词传递，四市场的发音、口音和口型仍需真实样片人工听看。

任务保存在 `.studio/studio.sqlite3`；图片在 `.studio/media/`；提示词与映射在 `.studio/projects/<id>/artifacts/`；视频在 `.studio/projects/<id>/renders/final.mp4`。上述内容均不提交 Git。视频成功 URL 有有效期，请保持本地服务运行以便及时下载。提交网络结果不明时标记“待确认”，避免自动重复扣费。

## 开发与测试

```bash
python -m venv .venv
# Windows: .venv\Scripts\python；Linux: .venv/bin/python
.venv/bin/python -m pip install -r requirements-studio.txt
.venv/bin/python -m studio
# 另一终端：
cd studio-web
pnpm install --frozen-lockfile
pnpm dev
```

后端：`.venv/bin/python -m pytest tests/studio -q`。前端：`pnpm test`、`pnpm typecheck`、`pnpm build`。外部服务边界使用受控响应，真实本地验证包含图片落盘、角色绑定、参数构造、任务持久化与重复提交；真实账号生成质量需配置凭证后联调。

多市场规格：`docs/multimarket-ugc-spec.md`；实施计划：`docs/superpowers/plans/2026-11-09-multimarket-ugc.md`；历史真实联调：`docs/live-deepseek-wavespeed-integration-2026-09-14.md`；前端组件来源：`studio-web/vendor/smoothui/`。

本改造沿用上游 AGPL-3.0，SmoothUI 组件许可单独保留；分发或托管时保留对应许可证。
