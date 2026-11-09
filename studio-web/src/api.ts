export const languages = { "pt-BR": "巴西葡语", "es-MX": "墨西哥西班牙语", "en-US": "美式英语", "fil-PH": "Filipino（菲律宾语）" } as const;
export type Language = keyof typeof languages;
export interface LanguageCheck { status: "ok" | "failed"; message?: string; results: { line: number; status: "match" | "likely_mismatch" | "uncertain"; message: string }[] }
export type Role = "character" | "scene" | "game";
export interface Asset {
  id: string;
  role: Role;
  name: string;
  url: string;
  width: number;
  height: number;
  is_default: boolean;
  source_url?: string;
}
export interface Settings {
  llm_base_url: string;
  llm_model: string;
  ark_model: string;
  video_provider: "wavespeed" | "flova" | "ark";
  wavespeed_model: string;
  wavespeed_resolution: string;
  flova_model: string;
  flova_resolution: string;
  flova_cli_path: string;
  pinterest_board_id: string;
  configured: { llm: boolean; wavespeed: boolean; flova: boolean; ark: boolean; pinterest: boolean };
  credential_storage: string;
}
export interface Job {
  id: string;
  theme: string;
  status: string;
  created_at: string;
  updated_at: string;
  error?: string;
  prompt?: string;
  video_url?: string;
  review_status?: string;
  task_id?: string;
  request: {
    language?: Language;
    language_warning?: string | null;
    character_id?: string;
    scene_id?: string;
    game_id?: string;
    batch_id?: string;
    variation_index?: number;
    variation_count?: number;
  };
  draft?: {
    title: string;
    hook: string;
    language?: Language;
    dialogue?: string;
    dialogue_pt_br?: string;
    scene_description: string;
    background_motion: string;
    ambience: string;
    beats: {
      start: number;
      end: number;
      action: string;
      camera: string;
      audio: string;
    }[];
  };
}
export interface SceneResults {
  items: { id: string; title: string; url: string; image_url: string }[];
  bookmark?: string;
  search_url: string;
  recommended_query?: string;
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, options);
  } catch {
    throw new Error("无法连接本地服务。请确认工作室服务已启动，然后重试。");
  }
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const body = await response.json();
      message =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail ?? body.error ?? message);
    } catch {}
    throw new Error(message);
  }
  return response.json();
}
export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, {
    method: "POST",
    ...(body === undefined
      ? {}
      : {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
  });
export function validateImage(file: File) {
  if (!file.type.startsWith("image/"))
    throw new Error("请选择图片文件（PNG、JPEG 或 WebP）。");
  if (file.size > 10 * 1024 * 1024)
    throw new Error("图片不能超过 10 MiB，请压缩后重试。");
}
export async function upload(file: File, role: Role) {
  validateImage(file);
  const form = new FormData();
  form.append("file", file);
  form.append("role", role);
  return api<Asset>("/assets", { method: "POST", body: form });
}
