import { afterEach, describe, it, expect, vi } from "vitest";
import {
  render,
  screen,
  waitFor,
  cleanup,
  fireEvent,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { upload } from "./api";
const settings = {
  llm_base_url: "https://api.deepseek.com",
  llm_model: "deepseek-v4-flash-vision-exp",
  video_provider: "wavespeed" as const,
  wavespeed_model: "bytedance/seedance-2.0-mini/text-to-video",
  wavespeed_resolution: "480p",
  flova_model: "Seedance 2.5",
  flova_resolution: "720p",
  flova_cli_path: "flova",
  ark_model: "seedance",
  pinterest_board_id: "",
  configured: { llm: false, wavespeed: false, flova: false, ark: false, pinterest: false },
  credential_storage: "keyring",
};
function mockFetch(extra?: (path: string, options?: RequestInit) => unknown) {
  return vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) => {
      const result = extra?.(path, options);
      if (result) return result;
      return {
        ok: true,
        json: async () => (path === "/api/settings" ? settings : []),
      };
    }),
  );
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
describe("studio", () => {
  it("describes the full four-second phone-screen hold", async () => {
    mockFetch();
    render(<App />);
    expect(await screen.findByText(/再稳定展示约 4 秒/)).toBeInTheDocument();
  });
  it("identifies the configured multimodal director model", async () => {
    mockFetch();
    render(<App />);
    await userEvent.click(screen.getByRole("tab", { name: "设置" }));
    expect(await screen.findByRole("heading", { name: "DeepSeek 视觉导演" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("deepseek-v4-flash-vision-exp")).toBeInTheDocument();
  });
  it("rejects non-image uploads before making a request", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await expect(
      upload(new File(["x"], "bad.txt", { type: "text/plain" }), "scene"),
    ).rejects.toThrow("请选择图片");
    expect(fetch).not.toHaveBeenCalled();
  });
  it("requires a theme and character before drafting", async () => {
    mockFetch();
    render(<App />);
    const button = await screen.findByRole("button", { name: /生成导演草稿/ });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(
      await screen.findByText("先填写这支视频的主题。"),
    ).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("视频主题"), "新游戏");
    await userEvent.click(button);
    expect(await screen.findByText(/请选择一张人物图片/)).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalledWith("/api/drafts/batch", expect.anything());
  });
  it("shows local service failure visibly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "无法连接本地服务",
    );
  });
  it("uploads one real multipart file and displays persisted reference", async () => {
    mockFetch((path, options) => {
      if (path === "/api/assets" && options?.method === "POST")
        return {
          ok: true,
          json: async () => ({
            id: "actor",
            role: "character",
            name: "actor.png",
            url: "/api/media/actor",
            width: 10,
            height: 20,
            is_default: false,
          }),
        };
    });
    const { container } = render(<App />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /生成导演草稿/ }),
      ).toBeEnabled(),
    );
    const file = new File(["image"], "actor.png", { type: "image/png" });
    fireEvent.change(container.querySelector("input[type=file]")!, {
      target: { files: [file] },
    });
    await waitFor(() =>
      expect(screen.getByText("10 × 20 · 已保存")).toBeInTheDocument(),
    );
    const calls = vi.mocked(fetch).mock.calls;
    const request = calls.find((c) => c[1]?.method === "POST")!;
    expect(request[1]?.body).toBeInstanceOf(FormData);
    expect((request[1]?.body as FormData).get("role")).toBe("character");
  });
  it("uses bundled character and scene without uploading or paying", async () => {
    const bundled = [
      { id: "built-actor", role: "character", name: "actor.jpg", url: "/api/media/built-actor", width: 600, height: 800, is_default: false, source_url: "builtin://character/actor.jpg" },
      { id: "built-room", role: "scene", name: "room.jpg", url: "/api/media/built-room", width: 600, height: 800, is_default: false, source_url: "builtin://scene/room.jpg" },
    ];
    let brief: Record<string, unknown> | undefined;
    mockFetch((path, options) => {
      if (path === "/api/assets") return { ok: true, json: async () => bundled };
      if (path === "/api/drafts/batch") {
        brief = JSON.parse(String(options?.body));
        return { ok: true, json: async () => [{ id: "draft", theme: "客厅游戏", status: "drafting", request: brief }] };
      }
    });
    render(<App />);
    await userEvent.type(screen.getByLabelText("视频主题"), "客厅游戏");
    await userEvent.click(screen.getByRole("tab", { name: "内置人物" }));
    await userEvent.click(screen.getByRole("button", { name: /选择人物 actor.jpg/ }));
    await userEvent.click(screen.getByRole("tab", { name: "内置场景" }));
    await userEvent.click(screen.getByRole("button", { name: /选择场景 room.jpg/ }));
    await userEvent.click(screen.getByRole("button", { name: /生成导演草稿/ }));

    await waitFor(() => expect(brief).toMatchObject({
      character_mode: "upload", character_ids: ["built-actor"], scene_ids: ["built-room"],
    }));
    expect(vi.mocked(fetch).mock.calls.some(([path, options]) =>
      path === "/api/assets" && options?.method === "POST",
    )).toBe(false);
    expect(vi.mocked(fetch).mock.calls.some(([path]) => String(path).includes("/generate"))).toBe(false);
  });
  it("rotates selected built-in scenes across a draft batch", async () => {
    const bundled = [
      { id: "actor", role: "character", name: "actor.webp", url: "/api/media/actor", source_url: "builtin://character/actor.webp" },
      { id: "room-a", role: "scene", name: "room-a.webp", url: "/api/media/room-a", source_url: "builtin://scene/room-a.webp" },
      { id: "room-b", role: "scene", name: "room-b.webp", url: "/api/media/room-b", source_url: "builtin://scene/room-b.webp" },
    ];
    let brief: { scene_ids: string[] } | undefined;
    mockFetch((path, options) => {
      if (path === "/api/assets") return { ok: true, json: async () => bundled };
      if (path === "/api/drafts/batch") {
        brief = JSON.parse(String(options?.body));
        return { ok: true, json: async () => [{ id: "batch-draft", theme: "不同客厅", status: "drafting", request: brief }] };
      }
    });
    render(<App />);
    await userEvent.type(screen.getByLabelText("视频主题"), "不同客厅");
    fireEvent.change(screen.getByLabelText("生成数量（1–10条）"), { target: { value: "2" } });
    await userEvent.click(screen.getByRole("tab", { name: "内置人物" }));
    await userEvent.click(screen.getByRole("button", { name: /选择人物 actor.webp/ }));
    await userEvent.click(screen.getByRole("tab", { name: "内置场景" }));
    await userEvent.click(screen.getByRole("button", { name: /选择场景 room-a.webp/ }));
    await userEvent.click(screen.getByRole("button", { name: /选择场景 room-b.webp/ }));
    await userEvent.click(screen.getByRole("button", { name: /生成导演草稿/ }));
    await waitFor(() => expect(brief?.scene_ids).toEqual(["room-a", "room-b"]));
  });
  it("shows provider errors from real draft form", async () => {
    mockFetch((path, options) => {
      if (path === "/api/assets" && options?.method === "POST")
        return {
          ok: true,
          json: async () => ({
            id: "scene",
            role: "scene",
            name: "scene.png",
            url: "/api/media/scene",
            width: 10,
            height: 10,
          }),
        };
      if (path === "/api/assets")
        return {
          ok: true,
          json: async () => [
            {
              id: "a",
              role: "character",
              is_default: true,
              name: "a",
              url: "/api/media/a",
            },
          ],
        };
      if (path === "/api/drafts/batch")
        return {
          ok: false,
          status: 400,
          json: async () => ({ detail: "请配置导演模型密钥" }),
        };
    });
    const { container } = render(<App />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /生成导演草稿/ }),
      ).toBeEnabled(),
    );
    await userEvent.click(screen.getByRole("tab", { name: "默认人物" }));
    await userEvent.type(screen.getByLabelText("视频主题"), "游戏");
    fireEvent.change(container.querySelector("input[type=file]")!, {
      target: { files: [new File(["x"], "scene.png", { type: "image/png" })] },
    });
    await screen.findByText("scene.png");
    await userEvent.click(screen.getByRole("button", { name: /生成导演草稿/ }));
    expect(await screen.findByText("请配置导演模型密钥")).toBeInTheDocument();
  });
  it("restores history without submitting generation", async () => {
    mockFetch((path) =>
      path === "/api/jobs"
        ? {
            ok: true,
            json: async () => [
              {
                id: "one",
                theme: "持久保存的主题",
                status: "failed",
                created_at: "2026-09-10T00:00:00Z",
                request: {},
                error: "失败",
              },
            ],
          }
        : undefined,
    );
    render(<App />);
    await userEvent.click(screen.getByRole("tab", { name: "作品与任务" }));
    expect(await screen.findByText("持久保存的主题")).toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.every((c) => !c[1]?.method)).toBe(true);
  });
});

it("checks language conservatively and invalidates stale replies when the market changes", async () => {
  let resolveCheck: (value: unknown) => void = () => {};
  mockFetch((path) => {
    if (path === "/api/language-check") return new Promise((resolve) => { resolveCheck = resolve; });
  });
  render(<App />);
  const market = screen.getByLabelText("市场 / 口播语言");
  expect(market).toHaveValue("pt-BR");
  const input = screen.getByLabelText("巴西葡语台词（可选）");
  fireEvent.change(input, { target: { value: "This is a complete English sentence" } });
  fireEvent.blur(input);
  await waitFor(() => expect(resolveCheck).not.toBeUndefined());
  await userEvent.selectOptions(market, "es-MX");
  expect(screen.getByLabelText("墨西哥西班牙语台词（可选）")).toHaveValue("This is a complete English sentence");
  resolveCheck({ ok: true, json: async () => ({ status: "ok", results: [{line: 1, status: "likely_mismatch", message: "过期提示"}] }) });
  await waitFor(() => expect(screen.queryByText("过期提示")).not.toBeInTheDocument());
});

it("submits the selected market and untrimmed nonempty dialogue after the warning", async () => {
  const bundled = [
    { id: "actor", role: "character", name: "actor.jpg", url: "/api/media/actor", source_url: "builtin://character/actor.jpg" },
    { id: "room", role: "scene", name: "room.jpg", url: "/api/media/room", source_url: "builtin://scene/room.jpg" },
  ];
  let brief: Record<string, unknown> | undefined;
  mockFetch((path, options) => {
    if (path === "/api/assets") return { ok: true, json: async () => bundled };
    if (path === "/api/language-check") return { ok: true, json: async () => ({status: "ok", results: [{line: 1, status: "likely_mismatch", message: "第 1 条台词可能是英语，请检查。"}]}) };
    if (path === "/api/drafts/batch") { brief = JSON.parse(String(options?.body)); return {ok: true, json: async () => [{id: "draft", theme: "主题", status: "drafting", request: brief}]}; }
  });
  render(<App />);
  await userEvent.type(screen.getByLabelText("视频主题"), "客厅游戏");
  await userEvent.click(screen.getByRole("tab", {name: "内置人物"}));
  await userEvent.click(screen.getByRole("button", {name: /选择人物 actor.jpg/}));
  await userEvent.click(screen.getByRole("tab", {name: "内置场景"}));
  await userEvent.click(screen.getByRole("button", {name: /选择场景 room.jpg/}));
  await userEvent.selectOptions(screen.getByLabelText("市场 / 口播语言"), "es-MX");
  const field = screen.getByLabelText("墨西哥西班牙语台词（可选）");
  fireEvent.change(field, {target: {value: "  This is an English sentence for you.  \n\n"}});
  fireEvent.blur(field);
  expect(await screen.findByText(/第 1 条台词可能是英语/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", {name: /生成导演草稿/}));
  await waitFor(() => expect(brief).toMatchObject({language: "es-MX", dialogue_lines: ["  This is an English sentence for you.  "], language_warnings: ["第 1 条台词可能是英语，请检查。"]}));
});

it("lets users retry a failed language check without editing the text", async () => {
  let calls = 0;
  mockFetch((path) => {
    if (path === "/api/language-check") {
      calls++;
      return {ok: true, json: async () => calls === 1
        ? {status: "failed", results: [], message: "语言检查失败"}
        : {status: "ok", results: [{line: 1, status: "match", message: "一致"}]}};
    }
  });
  render(<App />);
  const input = screen.getByLabelText("巴西葡语台词（可选）");
  fireEvent.change(input, {target: {value: "Esta é uma frase longa para testar agora"}});
  fireEvent.blur(input);
  expect(await screen.findByText("语言检查失败")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", {name: "重新检查台词语言"}));
  await waitFor(() => expect(calls).toBe(2));
  expect(await screen.findByText("台词语言检查完成。")).toBeInTheDocument();
});
