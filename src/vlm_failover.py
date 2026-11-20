from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from dotenv import load_dotenv
from PIL import Image


def load_project_env(env_path: Path | None = None) -> dict[str, str]:
    """
    Drive 또는 로컬 프로젝트의 .env에서 GEMINI_API_KEY, ANTHROPIC_API_KEY를 불러옵니다.
    """
    candidates = [
        env_path,
        Path("/content/drive/MyDrive/k12_math_rag_data/.env"),
        Path("/content/k12-math-rag-tutor/.env"),
        Path("D:/k12-math-rag-tutor/.env"),
        Path(".env"),
    ]
    for p in candidates:
        if p is not None and p.exists():
            load_dotenv(dotenv_path=p, override=True)
            break

    return {
        "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", "").strip(),
        "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", "").strip(),
    }


def is_quota_or_transient_error(err: Exception | str) -> bool:
    """
    503 UNAVAILABLE(일시 과부하) 또는 429 RESOURCE_EXHAUSTED(쿼터/요청 한도 초과) 등
    일시적 오류 또는 쿼터 소진 여부를 판별합니다.
    """
    msg = str(err).upper()
    triggers = [
        "503",
        "UNAVAILABLE",
        "429",
        "RESOURCE_EXHAUSTED",
        "QUOTA EXCEEDED",
        "HIGH DEMAND",
        "RATE LIMIT",
        "OVERLOADED",
    ]
    return any(t in msg for t in triggers)


def is_gemini_key_blocked_or_403(err: Exception | str) -> bool:
    """
    403 PERMISSION_DENIED 또는 API 키 유출(LEAKED) 등으로 Gemini 키가 차단된 경우를 판별합니다.
    """
    msg = str(err).upper()
    block_triggers = [
        "403",
        "PERMISSION_DENIED",
        "API KEY WAS REPORTED AS LEAKED",
        "REPORTED AS LEAKED",
        "API_KEY_INVALID",
    ]
    return any(t in msg for t in block_triggers)


def should_failover_to_claude(err: Exception | str) -> bool:
    """
    503 / 429 뿐만 아니라 403 / PERMISSION_DENIED / LEAKED 발생 시에도
    Claude로 즉시 페일오버해야 하는지 판별합니다.
    """
    return is_quota_or_transient_error(err) or is_gemini_key_blocked_or_403(err)


def _image_to_png_bytes_and_b64(image_input: Any) -> tuple[bytes, str]:
    """
    PIL.Image, 파일 경로(Path/str), bytes 입력을 PNG 바이트 및 base64 문자열로 변환합니다.
    """
    if isinstance(image_input, Image.Image):
        img = image_input.convert("RGB")
    elif isinstance(image_input, (str, Path)):
        img = Image.open(image_input).convert("RGB")
    elif isinstance(image_input, bytes):
        img = Image.open(io.BytesIO(image_input)).convert("RGB")
    else:
        raise TypeError(f"지원하지 않는 이미지 타입입니다: {type(image_input)}")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw_bytes = buf.getvalue()
    b64_str = base64.b64encode(raw_bytes).decode("utf-8")
    return raw_bytes, b64_str


def call_gemini_vision(
    prompt: str,
    image_input: Any,
    gemini_model: str = "gemini-2.5-flash",
    api_key: str | None = None,
) -> str:
    """
    google-genai SDK로 Gemini 멀티모달 호출을 수행합니다.
    """
    from google import genai
    from google.genai import types

    key = (api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY가 설정되어 있지 않습니다.")

    img_bytes, _ = _image_to_png_bytes_and_b64(image_input)
    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model=gemini_model,
        contents=[
            types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
            prompt,
        ],
    )
    return (response.text or "").strip()


def call_claude_vision(
    prompt: str,
    image_input: Any,
    claude_model: str = "claude-sonnet-4-5",
    api_key: str | None = None,
) -> str:
    """
    anthropic SDK로 Claude Vision 멀티모달 호출을 수행합니다.
    """
    import anthropic

    key = (api_key or os.environ.get("ANTHROPIC_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되어 있지 않습니다.")

    _, b64_str = _image_to_png_bytes_and_b64(image_input)
    client = anthropic.Anthropic(api_key=key)
    message = client.messages.create(
        model=claude_model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64_str,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    )
    chunks: list[str] = []
    for block in message.content:
        if getattr(block, "type", None) == "text":
            chunks.append(block.text)
    return "\n".join(chunks).strip()


class VLMFailoverRunner:
    """
    Gemini를 우선 호출하되, 503/429 또는 403/PERMISSION_DENIED/LEAKED 발생 시
    즉시 Claude로 전환해 파이프라인을 멈추지 않고 이어가도록 돕는 러너입니다.
    """

    def __init__(
        self,
        gemini_model: str = "gemini-2.5-flash",
        claude_model: str = "claude-sonnet-4-5",
        stick_to_claude_on_quota: bool = True,
        stick_to_claude_on_block: bool = True,
        env_path: Path | None = None,
    ) -> None:
        keys = load_project_env(env_path)
        self.gemini_key = keys["GEMINI_API_KEY"]
        self.claude_key = keys["ANTHROPIC_API_KEY"]
        self.gemini_model = gemini_model
        self.claude_model = claude_model
        self.stick_to_claude_on_quota = stick_to_claude_on_quota
        self.stick_to_claude_on_block = stick_to_claude_on_block
        self.prefer_claude = not bool(self.gemini_key)

    def generate(self, prompt: str, image_input: Any, page_label: str = "") -> tuple[str, str]:
        """
        반환값: (추출된_텍스트, 실제_사용된_백엔드_이름)
        """
        prefix = f"[{page_label}] " if page_label else ""

        if not self.prefer_claude and self.gemini_key:
            try:
                text = call_gemini_vision(
                    prompt=prompt,
                    image_input=image_input,
                    gemini_model=self.gemini_model,
                    api_key=self.gemini_key,
                )
                return text, f"gemini:{self.gemini_model}"
            except Exception as exc:
                if should_failover_to_claude(exc) and self.claude_key:
                    err_upper = str(exc).upper()
                    is_blocked = is_gemini_key_blocked_or_403(err_upper)
                    is_quota = "429" in err_upper or "RESOURCE_EXHAUSTED" in err_upper

                    if is_blocked and self.stick_to_claude_on_block:
                        self.prefer_claude = True
                        print(
                            f"{prefix}Gemini 403/키 차단 감지(LEAKED/PERMISSION_DENIED) -> "
                            f"이후 요청도 즉시 Claude({self.claude_model})로 전환합니다."
                        )
                    elif is_quota and self.stick_to_claude_on_quota:
                        self.prefer_claude = True
                        print(
                            f"{prefix}Gemini 429 쿼터 초과 감지 -> "
                            f"이후 요청도 즉시 Claude({self.claude_model})로 전환합니다."
                        )
                    else:
                        print(
                            f"{prefix}Gemini 503/429/403 감지 -> "
                            f"즉시 Claude({self.claude_model})로 전환합니다."
                        )
                else:
                    raise

        if not self.claude_key:
            raise RuntimeError("ANTHROPIC_API_KEY가 없어 Claude로 전환할 수 없습니다.")

        text = call_claude_vision(
            prompt=prompt,
            image_input=image_input,
            claude_model=self.claude_model,
            api_key=self.claude_key,
        )
        return text, f"claude:{self.claude_model}"


def install_claude_failover_hook(
    gemini_model: str = "gemini-2.5-flash",
    claude_model: str = "claude-sonnet-4-5",
    env_path: Path | None = None,
) -> VLMFailoverRunner:
    """
    google-genai Client.models.generate_content 호출을 가로채어
    429 / 503 / 403 발생 시 Claude Vision 응답 객체로 즉시 대체합니다.
    """
    from google import genai

    runner = VLMFailoverRunner(
        gemini_model=gemini_model,
        claude_model=claude_model,
        stick_to_claude_on_quota=True,
        stick_to_claude_on_block=True,
        env_path=env_path,
    )

    models_cls = genai.models.Models
    if getattr(models_cls, "_claude_failover_patched", False):
        return runner

    orig_generate_content = models_cls.generate_content

    def _extract_prompt_and_images(contents: Any) -> tuple[str, list[Any]]:
        prompts: list[str] = []
        images: list[Any] = []
        items = contents if isinstance(contents, list) else [contents]
        for item in items:
            if isinstance(item, str):
                prompts.append(item)
            elif isinstance(item, Image.Image):
                images.append(item)
            elif hasattr(item, "inline_data") and getattr(getattr(item, "inline_data", None), "data", None):
                images.append(item.inline_data.data)
            elif isinstance(item, dict) and "text" in item:
                prompts.append(str(item["text"]))
        return "\n".join(prompts).strip(), images

    def _patched_generate_content(self, *args, **kwargs):
        try:
            return orig_generate_content(self, *args, **kwargs)
        except Exception as exc:
            if not (should_failover_to_claude(exc) and runner.claude_key):
                raise

            runner.prefer_claude = True
            contents = kwargs.get("contents")
            if contents is None and len(args) >= 2:
                contents = args[1]

            prompt, images = _extract_prompt_and_images(contents)
            if not images:
                raise

            text, _ = runner.generate(
                prompt=prompt or "이미지의 수식과 내용을 정확히 추출해 주세요.",
                image_input=images[0],
                page_label="failover:claude",
            )
            return SimpleNamespace(text=text)

    models_cls.generate_content = _patched_generate_content
    models_cls._claude_failover_patched = True
    return runner