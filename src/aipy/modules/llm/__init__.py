"""LLM access port and adapters for content generation.

A content run is generated through a :class:`ModelGateway`. Two adapters ship:

* :class:`HttpModelGateway` - talks to any OpenAI-compatible chat completions
  endpoint (OpenAI, DeepSeek, 通义/智谱, local vLLM). This is the real path used
  in staging/production once ``AIPY_LLM__*`` is configured.
* :class:`StubModelGateway` - deterministic demo text with no network call, so
  the worker runs end-to-end in local/test and CI without API keys.

:func:`select_gateway` picks the adapter: a configured endpoint wins, otherwise
local/test fall back to the stub, and any other environment without a provider
fails fast instead of leaking demo text to users.
"""

from typing import cast

from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from aipy.shared.config import AppSettings, LlmSettings


class ModelRequest(BaseModel):
    prompt: str
    system: str | None = None
    max_tokens: int = 1024


class ModelResult(BaseModel):
    text: str


class ModelGateway:
    """Protocol for text generation.

    Subclasses implement :meth:`complete`. The base raises so a half-wired
    adapter fails loudly instead of silently returning nothing.
    """

    def complete(self, request: ModelRequest) -> ModelResult:  # pragma: no cover - interface
        raise NotImplementedError


class HttpModelGateway(ModelGateway):
    """OpenAI-compatible chat completions client.

    The ``openai`` SDK is imported lazily so environments that only use the stub
    (and have no network) never pay for the import or the hard dependency at
    module load time.
    """

    def __init__(self, settings: LlmSettings) -> None:
        from openai import OpenAI

        self._client = OpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key.get_secret_value() if settings.api_key else "",
            timeout=settings.timeout,
        )
        self._model = settings.model or ""

    def complete(self, request: ModelRequest) -> ModelResult:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        response = self._client.chat.completions.create(
            model=self._model,
            messages=cast(list[ChatCompletionMessageParam], messages),
            max_tokens=request.max_tokens,
        )
        text = response.choices[0].message.content or ""
        return ModelResult(text=text)


class StubModelGateway(ModelGateway):
    """Deterministic stand-in: echoes a templated paragraph, no I/O.

    Used in local/test and CI so the async workflow path is exercisable without
    credentials or a network round-trip.
    """

    def complete(self, request: ModelRequest) -> ModelResult:
        head = request.system or "AI 写作助手"
        body = request.prompt.replace("\n", " ").strip() or "（无具体指令）"
        return ModelResult(
            text=(
                f"【{head}】根据要求「{body[:120]}」生成的演示内容片段："
                "本段用于验证工作流异步执行与状态回写链路，不依赖真实模型。"
            )
        )


def select_gateway(settings: AppSettings) -> ModelGateway:
    """Pick the gateway for the current environment.

    A configured OpenAI-compatible endpoint always wins. When it is absent,
    local/test fall back to the stub so the workflow still runs without keys;
    any other environment raises deliberately so a missing integration fails
    fast in staging/prod rather than silently echoing demo text to users.
    """

    if settings.llm_configured:
        return HttpModelGateway(settings.llm)
    if settings.environment in ("local", "test"):
        return StubModelGateway()
    raise RuntimeError(
        f"no ModelGateway configured for environment={settings.environment!r}; "
        "set AIPY_LLM__BASE_URL / AIPY_LLM__API_KEY / AIPY_LLM__MODEL to generate real content"
    )
