from typing import Annotated, Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from .languages import Language

ExactText = Annotated[str, StringConstraints(strip_whitespace=False)]


class Brief(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    language: Language = 'pt-BR'
    theme: str = Field(min_length=2, max_length=2000)
    character_mode: Literal['upload', 'default'] = 'upload'
    character_id: str | None = None
    scene_id: str = Field(min_length=1, max_length=100)
    game_id: str | None = None
    dialogue_override: ExactText | None = Field(default=None, max_length=500)
    language_warning: str | None = Field(default=None, max_length=500)
    variation_index: int = Field(default=1, ge=1, le=10)
    variation_count: int = Field(default=1, ge=1, le=10)
    variation_direction: str = Field(default='', max_length=500)
    batch_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')

    @model_validator(mode='after')
    def check_character(self):
        if self.character_mode == 'upload' and not self.character_id:
            raise ValueError('请上传一张人物照片。')
        return self


VARIATION_DIRECTIONS = [
    '突然闯入画面：首帧已在快步走近，镜头短促后退接住人物，再随手机动作停稳。',
    '神秘制止动作：首帧手指压唇靠近镜头，镜头侧移追随人物退回场景。',
    '道具反应钩子：首帧人物被现有道具或环境变化打断，镜头快速推近反应后立即随行。',
    '环境冲击钩子：风、振动、灯光或物件运动在首帧造成可见后果，镜头小幅弧线绕行。',
    '失手与补救：首帧人物正在接住或稳住场内物件，镜头俯仰跟动后回到面部。',
    '被抓个正着：首帧人物猛地回头看向镜头，摄影者一步追近，再与人物并行。',
    '紧急分享：首帧人物把镜头引向一侧，镜头用一次果断横移显示场景线索。',
    '视线误导：首帧人物看向画外后迅速转回对镜头开口，镜头先跟视线再拉回。',
    '近距离反差：首帧是动作中的近景，镜头快速拉到中近景交代空间，不停顿。',
    '声音触发：首帧场内真实声响使人物立即停手、看向镜头并开口，镜头短促追踪。',
]


class BatchBrief(BaseModel):
    """One creative request expanded into independently reviewable paid jobs."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    language: Language = 'pt-BR'
    theme: str = Field(min_length=2, max_length=2000)
    count: int = Field(default=1, ge=1, le=10)
    character_mode: Literal['upload', 'default'] = 'upload'
    character_ids: list[str] = Field(default_factory=list, max_length=10)
    scene_ids: list[str] = Field(min_length=1, max_length=10)
    game_ids: list[str] = Field(default_factory=list, max_length=10)
    dialogue_lines: list[ExactText] = Field(default_factory=list, max_length=10)
    language_warnings: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode='after')
    def validate_pools(self):
        if self.character_mode == 'upload' and not self.character_ids:
            raise ValueError('请至少上传一张人物照片。')
        if self.dialogue_lines and len(self.dialogue_lines) != self.count:
            raise ValueError('手动台词需要每条视频一行，行数必须与生成数量一致。')
        if self.language_warnings and len(self.language_warnings) != self.count:
            raise ValueError('语言提示须与视频数量一致。')
        if len(set(self.scene_ids)) != len(self.scene_ids):
            raise ValueError('场景池中不要重复选择同一张图。')
        return self

    def expand(self):
        briefs = []
        batch_id = uuid4().hex if self.count > 1 else None
        for index in range(self.count):
            actor = None if self.character_mode == 'default' else self.character_ids[index % len(self.character_ids)]
            game = self.game_ids[index % len(self.game_ids)] if self.game_ids else None
            briefs.append(Brief(
                theme=self.theme, language=self.language, character_mode=self.character_mode, character_id=actor,
                scene_id=self.scene_ids[index % len(self.scene_ids)], game_id=game,
                dialogue_override=self.dialogue_lines[index] if self.dialogue_lines else None,
                language_warning=self.language_warnings[index] if self.language_warnings else None,
                variation_index=index + 1, variation_count=self.count,
                variation_direction=VARIATION_DIRECTIONS[index],
                batch_id=batch_id,
            ))
        return briefs


class BatchGenerate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    job_ids: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode='after')
    def unique_jobs(self):
        if len(set(self.job_ids)) != len(self.job_ids):
            raise ValueError('批量任务中不能包含重复的任务 ID。')
        return self


class Beat(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    start: float = Field(ge=0, lt=15)
    end: float = Field(gt=0, le=15)
    action: str = Field(min_length=4, max_length=1400)
    camera: str = Field(min_length=4, max_length=1000)
    audio: str = Field(min_length=4, max_length=1000)


class Draft(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    language: Language = 'pt-BR'
    title: str = Field(min_length=1, max_length=150)
    hook: str = Field(min_length=1, max_length=1000)
    dialogue: ExactText = Field(min_length=1, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def legacy_dialogue(cls, value):
        if isinstance(value, dict) and "dialogue_pt_br" in value:
            value = dict(value)
            old = value.pop("dialogue_pt_br")
            if "dialogue" in value and value["dialogue"] != old:
                raise ValueError("dialogue 与旧 dialogue_pt_br 字段冲突。")
            value.setdefault("dialogue", old)
        return value

    @property
    def dialogue_pt_br(self):
        return self.dialogue
    scene_description: str = Field(min_length=4, max_length=1000)
    background_motion: str = Field(min_length=4, max_length=1000)
    ambience: str = Field(min_length=4, max_length=1000)
    beats: list[Beat] = Field(min_length=4, max_length=4)

    @model_validator(mode='after')
    def validate_timeline(self):
        windows = [(0, 1.5), (1.5, 8.5), (8.5, 11), (11, 15)]
        if [(b.start, b.end) for b in self.beats] != windows:
            raise ValueError('时间线必须连续覆盖 0–15 秒，且保留最后 4 秒屏幕展示。')
        if len(self.dialogue_pt_br.split()) > 30:
            raise ValueError('口播过长，请压缩至约 7 秒可自然说完的台词。')
        return self


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    llm_base_url: str | None = Field(default=None, max_length=500)
    llm_model: str | None = Field(default=None, max_length=200)
    ark_model: str | None = Field(default=None, max_length=200)
    video_provider: Literal['wavespeed', 'flova', 'ark'] | None = None
    wavespeed_model: Literal['bytedance/seedance-2.0-mini/text-to-video'] | None = None
    wavespeed_resolution: Literal['480p'] | None = None
    flova_model: Literal['Seedance 2.5'] | None = None
    flova_resolution: Literal['720p'] | None = None
    flova_cli_path: str | None = Field(default=None, max_length=500)
    pinterest_board_id: str | None = Field(default=None, max_length=100)
    llm_api_key: str | None = Field(default=None, max_length=1000)
    ark_api_key: str | None = Field(default=None, max_length=1000)
    wavespeed_api_key: str | None = Field(default=None, max_length=1000)
    flova_api_key: str | None = Field(default=None, max_length=1000)
    pinterest_access_token: str | None = Field(default=None, max_length=2000)


class SceneSearch(BaseModel):
    language: Language = 'pt-BR'
    query: str = Field(default='', max_length=300)
    bookmark: str | None = Field(default=None, max_length=2000)


class SceneImport(BaseModel):
    pin_id: str = Field(pattern=r'^\d{1,40}$')


class LanguageCheckRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    language: Language = 'pt-BR'
    dialogue_lines: list[Annotated[str, StringConstraints(max_length=500)]] = Field(default_factory=list, max_length=10)
