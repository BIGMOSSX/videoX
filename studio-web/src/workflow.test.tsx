import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  waitFor,
  fireEvent,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { shouldPoll } from "./status";
import type { Job } from "./api";

const settings = {
  llm_base_url: "https://example.com",
  llm_model: "director",
  video_provider: "wavespeed" as const,
  wavespeed_model: "bytedance/seedance-2.0-mini/text-to-video",
  wavespeed_resolution: "480p",
  flova_model: "Seedance 2.5",
  flova_resolution: "720p",
  flova_cli_path: "flova",
  ark_model: "test-model",
  pinterest_board_id: "board",
  configured: { llm: true, wavespeed: true, flova: false, ark: true, pinterest: true },
  credential_storage: "keyring",
};
const job: Job = {
  id: "draft",
  theme: "待审核草稿",
  status: "draft_ready",
  created_at: "2026-09-10T00:00:00Z",
  updated_at: "2026-09-10T00:00:00Z",
  request: {},
  draft: {
    title: "审核标题",
    hook: "咖啡蒸汽吸引视线",
    dialogue_pt_br: "Olá!",
    scene_description: "Café",
    background_motion: "Steam",
    ambience: "Café",
    beats: [],
  },
};
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("locks duplicate video submission while the request is pending", async () => {
  let submissions = 0;
  let resolveGeneration: (value: unknown) => void = () => {};
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      if (path.endsWith("/generate")) {
        submissions++;
        return new Promise((resolve) => {
          resolveGeneration = resolve;
        });
      }
      return {
        ok: true,
        json: async () =>
          path === "/api/settings"
            ? settings
            : path === "/api/jobs"
              ? [job]
              : [],
      };
    }),
  );
  render(<App />);
  await userEvent.click(screen.getByRole("tab", { name: "作品与任务" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "查看详情" }),
  );
  const button = screen.getByRole("button", { name: /确认草稿，提交视频/ });
  fireEvent.click(button);
  fireEvent.click(button);
  expect(submissions).toBe(1);
  expect(button).toBeDisabled();
  expect(screen.getByText(/WaveSpeed · Seedance 2.0 Mini · 480p/)).toBeInTheDocument();
  resolveGeneration({
    ok: true,
    json: async () => ({ ...job, status: "queued" }),
  });
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: /确认草稿，提交视频/ }),
    ).not.toBeInTheDocument(),
  );
});
it("uses the theme when optional Pinterest keywords are empty", async () => {
  let searchBody = "";
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) => {
      if (path === "/api/scenes/search") {
        searchBody = String(options?.body);
        return {
          ok: true,
          json: async () => ({
            items: [],
            search_url: "https://www.pinterest.com/search/pins/",
            recommended_query: "cafeteria brasileira",
          }),
        };
      }
      return {
        ok: true,
        json: async () => (path === "/api/settings" ? settings : []),
      };
    }),
  );
  render(<App />);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: /生成导演草稿/ })).toBeEnabled(),
  );
  await userEvent.type(screen.getByLabelText("视频主题"), "咖啡厅分享游戏");
  await userEvent.click(screen.getByRole("tab", { name: "Pinterest" }));
  await userEvent.click(screen.getByRole("button", { name: /查找场景/ }));
  await screen.findByText("建议搜索：cafeteria brasileira");
  expect(JSON.parse(searchBody).query).toBe("咖啡厅分享游戏");
});
it("polls uncertain submissions only when a task id exists", () => {
  expect(shouldPoll({ ...job, status: "submission_unknown" })).toBe(false);
  expect(
    shouldPoll({
      ...job,
      status: "submission_unknown",
      task_id: "provider-id",
    }),
  ).toBe(true);
});

it("reviews historical references from the job even after the default changes", async () => {
  const assets = [
    { id: "actor-a", role: "character", name: "Actor A", url: "/api/media/a", is_default: false },
    { id: "actor-b", role: "character", name: "Actor B", url: "/api/media/b", is_default: true },
    { id: "scene-a", role: "scene", name: "Scene A", url: "/api/media/s" },
    { id: "game-a", role: "game", name: "Game A", url: "/api/media/g" },
  ];
  vi.stubGlobal("fetch", vi.fn(async (path: string) => ({ ok: true, json: async () =>
    path === "/api/settings" ? settings : path === "/api/assets" ? assets : path === "/api/jobs" ?
    [{ ...job, request: { character_id: "actor-a", scene_id: "scene-a", game_id: "game-a" } }] : []
  })));
  render(<App />);
  await userEvent.click(screen.getByRole("tab", { name: "作品与任务" }));
  await userEvent.click(await screen.findByRole("button", { name: "查看详情" }));
  expect(screen.getByRole("img", { name: "本任务人物参考：Actor A" })).toHaveAttribute("src", "/api/media/a");
  expect(screen.getByRole("img", { name: "本任务场景参考：Scene A" })).toHaveAttribute("src", "/api/media/s");
  expect(screen.getByRole("img", { name: "本任务游戏参考：Game A" })).toHaveAttribute("src", "/api/media/g");
  expect(screen.queryByRole("img", { name: /本任务人物参考：Actor B/ })).not.toBeInTheDocument();
});

it("shows the persisted human QC note beside a completed video", async () => {
  const completed = {
    ...job,
    status: "succeeded",
    video_url: "/api/videos/draft",
    review_status: "屏幕顶部出现了参考图没有的小数字，发布前需处理。",
  };
  vi.stubGlobal("fetch", vi.fn(async (path: string) => ({ ok: true, json: async () =>
    path === "/api/settings" ? settings : path === "/api/jobs" ? [completed] : []
  })));
  render(<App />);
  await userEvent.click(screen.getByRole("tab", { name: "作品与任务" }));
  await userEvent.click(await screen.findByRole("button", { name: "查看详情" }));
  expect(screen.getByText(completed.review_status)).toBeInTheDocument();
});

it("submits an approved multi-draft batch with one paid action", async () => {
  const actor = { id: "actor", role: "character", name: "Actor", url: "/api/media/actor", is_default: true };
  const scene = { id: "scene", role: "scene", name: "Scene", url: "/api/media/scene", width: 600, height: 800, is_default: false };
  const drafts = [1, 2].map((index) => ({
    ...job,
    id: `draft-${index}`,
    theme: "两条不同创意",
    status: "draft_ready",
    request: { character_id: actor.id, scene_id: scene.id, batch_id: "a".repeat(32), variation_index: index, variation_count: 2 },
    draft: { ...job.draft!, title: `创意 ${index}` },
  }));
  let batchBody: { job_ids: string[] } | undefined;
  vi.stubGlobal("fetch", vi.fn(async (path: string, options?: RequestInit) => {
    if (path === "/api/settings") return { ok: true, json: async () => settings };
    if (path === "/api/assets" && options?.method === "POST") return { ok: true, json: async () => scene };
    if (path === "/api/assets") return { ok: true, json: async () => [actor] };
    if (path === "/api/jobs") return { ok: true, json: async () => [] };
    if (path === "/api/drafts/batch") return { ok: true, json: async () => drafts };
    if (path === "/api/jobs/generate-batch") {
      batchBody = JSON.parse(String(options?.body));
      return { ok: true, json: async () => drafts.map((item) => ({ ...item, status: "submitting" })) };
    }
    throw new Error(`unexpected request: ${path}`);
  }));

  const { container } = render(<App />);
  await waitFor(() => expect(screen.getByRole("button", { name: /生成导演草稿/ })).toBeEnabled());
  await userEvent.click(screen.getByRole("tab", { name: "默认人物" }));
  await userEvent.type(screen.getByLabelText("视频主题"), "两条不同创意");
  fireEvent.change(screen.getByLabelText("生成数量（1–10条）"), { target: { value: "2" } });
  fireEvent.change(container.querySelector("input[type=file]")!, {
    target: { files: [new File(["scene"], "scene.png", { type: "image/png" })] },
  });
  await screen.findByText("600 × 800 · 已保存");
  await userEvent.click(screen.getByRole("button", { name: /生成导演草稿/ }));

  const submitBatch = await screen.findByRole("button", { name: /确认并提交本批 2 条视频/ });
  await userEvent.click(submitBatch);
  await waitFor(() => expect(batchBody).toEqual({ job_ids: ["draft-1", "draft-2"] }));
  expect(screen.getByText(/本批 2 条已进入提交队列/)).toBeInTheDocument();
});

it("ignores old-market Pinterest search responses after a market change", async () => {
  let resolveSearch: (value: unknown) => void = () => {};
  let started = false;
  vi.stubGlobal("fetch", vi.fn(async (path: string) => {
    if (path === "/api/scenes/search") {
      started = true;
      return new Promise((resolve) => { resolveSearch = resolve; });
    }
    return {ok: true, json: async () => path === "/api/settings" ? settings : []};
  }));
  render(<App />);
  await userEvent.type(screen.getByLabelText("视频主题"), "厨房场景");
  await userEvent.click(screen.getByRole("tab", {name: "Pinterest"}));
  await userEvent.click(screen.getByRole("button", {name: /查找场景/}));
  await waitFor(() => expect(started).toBe(true));
  await userEvent.selectOptions(screen.getByLabelText("市场 / 口播语言"), "es-MX");
  resolveSearch({ok: true, json: async () => ({items: [], search_url: "https://example.com", recommended_query: "过期市场结果", bookmark: "old-page"})});
  await waitFor(() => expect(screen.getByRole("button", {name: /查找场景/})).toBeEnabled());
  expect(screen.queryByText(/过期市场结果/)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", {name: "更多候选"})).not.toBeInTheDocument();
});

it("ignores a pending old-market Pinterest pagination response", async () => {
  let resolveMore: (value: unknown) => void = () => {};
  let calls = 0;
  vi.stubGlobal("fetch", vi.fn(async (path: string) => {
    if (path === "/api/scenes/search") {
      calls++;
      if (calls === 1) return {ok: true, json: async () => ({items: [], search_url: "https://example.com", bookmark: "page-2"})};
      return new Promise((resolve) => { resolveMore = resolve; });
    }
    return {ok: true, json: async () => path === "/api/settings" ? settings : []};
  }));
  render(<App />);
  await userEvent.type(screen.getByLabelText("视频主题"), "厨房场景");
  await userEvent.click(screen.getByRole("tab", {name: "Pinterest"}));
  await userEvent.click(screen.getByRole("button", {name: /查找场景/}));
  await userEvent.click(await screen.findByRole("button", {name: "更多候选"}));
  await waitFor(() => expect(calls).toBe(2));
  await userEvent.selectOptions(screen.getByLabelText("市场 / 口播语言"), "en-US");
  resolveMore({ok: true, json: async () => ({items: [], search_url: "https://example.com", recommended_query: "过期分页", bookmark: "page-3"})});
  await waitFor(() => expect(screen.getByRole("button", {name: /查找场景/})).toBeEnabled());
  expect(screen.queryByText(/过期分页/)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", {name: "更多候选"})).not.toBeInTheDocument();
});
