"""OpenAI HTTP transport for generated text and notification images."""

from __future__ import annotations

import base64
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .discord import http_error_excerpt, redact_secrets, truncate_text

try:
    from ..observability.operations import record_external_call
except ImportError:  # pragma: no cover
    from observability.operations import record_external_call


UrlOpener = Callable[..., Any]
Logger = Callable[..., None]
ImageAttachment = tuple[bytes, str, str]
Sleeper = Callable[[float], None]


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str = ""
    text_model: str = "gpt-4.1-mini"
    text_timeout_seconds: int = 45
    image_model: str = "gpt-image-2"
    image_size: str = "1536x1024"
    image_quality: str = "high"
    image_format: str = "jpeg"
    image_timeout_seconds: int = 120
    reference_image_timeout_seconds: int = 20
    reference_image_max_bytes: int = 6_000_000
    reference_image_max_retries: int = 2
    reference_image_retry_base_seconds: float = 0.25
    generated_image_max_bytes: int = 10_000_000
    max_text_prompt_chars: int = 12_000
    max_text_output_chars: int = 4_000
    image_generation_enabled: bool = False


class OpenAIIntegration:
    def __init__(
        self,
        config: OpenAIConfig,
        *,
        opener: UrlOpener = urlopen,
        log_error: Optional[Logger] = None,
        sleeper: Sleeper = time.sleep,
    ):
        self.config = config
        self._open = opener
        self._log_error = log_error or (lambda *_args: None)
        self._sleep = sleeper

    def generate_image(
        self,
        prompt: str,
        *,
        reference_image_url: Optional[str] = None,
        fallback_prompt: Optional[str] = None,
    ) -> Optional[ImageAttachment]:
        if not prompt.strip() or not self.config.image_generation_enabled or not self.config.api_key:
            return None
        if reference_image_url:
            reference_image = self.fetch_reference_image(reference_image_url)
            if reference_image:
                generated = self._generate_image_from_reference(prompt, reference_image)
                if generated:
                    return generated
        return self._generate_image_from_prompt(fallback_prompt or prompt)

    def text_response(
        self,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int = 700,
    ) -> Optional[str]:
        if not self.config.api_key:
            return None
        system_prompt = truncate_text(system_prompt, self.config.max_text_prompt_chars)
        user_prompt = truncate_text(user_prompt, self.config.max_text_prompt_chars)
        payload: Dict[str, Any] = {
            "model": self.config.text_model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
            ],
            "max_output_tokens": max(100, min(2000, int(max_output_tokens))),
        }
        try:
            response = self._post_json("https://api.openai.com/v1/responses", payload, self.config.text_timeout_seconds)
            direct = str(response.get("output_text") or "").strip()
            if direct:
                return truncate_text(direct, self.config.max_text_output_chars)
            for item in response.get("output", []):
                if not isinstance(item, dict):
                    continue
                for content in item.get("content", []) or []:
                    if isinstance(content, dict):
                        text = str(content.get("text") or "").strip()
                        if text:
                            return truncate_text(text, self.config.max_text_output_chars)
        except HTTPError as err:
            self._log_error("OpenAI owner interview text generation failed: %s", http_error_excerpt(err))
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as err:
            self._log_error(
                "OpenAI owner interview text generation failed: %s",
                redact_secrets(err, extra_secrets=[self.config.api_key]),
            )
        return None

    def fetch_reference_image(self, image_url: str) -> Optional[ImageAttachment]:
        image_url = str(image_url or "").strip()
        if not image_url:
            return None
        parsed = urlparse(image_url)
        if parsed.scheme not in {"http", "https"}:
            self._log_error("OpenAI reference image skipped: unsupported URL scheme")
            return None
        request = Request(image_url, headers={"User-Agent": "anba-excel/1.0"}, method="GET")
        max_attempts = max(1, int(self.config.reference_image_max_retries) + 1)
        last_error: Optional[str] = None
        try:
            for attempt in range(max_attempts):
                try:
                    started = time.perf_counter()
                    ok = False
                    with self._open(request, timeout=self.config.reference_image_timeout_seconds) as response:
                        content_type = str(response.headers.get("Content-Type") or "")
                        image_bytes = response.read(self.config.reference_image_max_bytes + 1)
                    ok = True
                    record_external_call("openai", "reference_image_get", time.perf_counter() - started, ok=ok)
                    if len(image_bytes) > self.config.reference_image_max_bytes:
                        self._log_error("OpenAI reference image skipped: file exceeds configured max size")
                        return None
                    image_ext, mime_type = self._reference_image_mime_type(content_type, parsed.path)
                    return image_bytes, f"reference.{image_ext}", mime_type
                except HTTPError as err:
                    record_external_call("openai", "reference_image_get", time.perf_counter() - started, ok=False, status_code=getattr(err, "code", ""))
                    last_error = http_error_excerpt(err)
                    if not self._retryable_http_error(err) or attempt >= max_attempts - 1:
                        break
                    self._sleep(self._retry_delay_seconds(attempt))
                except (URLError, TimeoutError, OSError, ValueError) as err:
                    record_external_call("openai", "reference_image_get", time.perf_counter() - started, ok=False, error_classification=err.__class__.__name__)
                    last_error = redact_secrets(err, extra_secrets=[self.config.api_key])
                    if attempt >= max_attempts - 1:
                        break
                    self._sleep(self._retry_delay_seconds(attempt))
        except HTTPError as err:
            last_error = http_error_excerpt(err)
        except (URLError, TimeoutError, OSError, ValueError) as err:
            last_error = redact_secrets(err, extra_secrets=[self.config.api_key])
        if last_error:
            self._log_error("OpenAI reference image fetch failed: %s", last_error)
        return None

    @staticmethod
    def _retryable_http_error(err: HTTPError) -> bool:
        return int(getattr(err, "code", 0) or 0) in {408, 429} or int(getattr(err, "code", 0) or 0) >= 500

    def _retry_delay_seconds(self, attempt: int) -> float:
        return min(2.0, max(0.0, float(self.config.reference_image_retry_base_seconds)) * (2 ** max(0, int(attempt))))

    def _generate_image_from_reference(
        self,
        prompt: str,
        reference_image: ImageAttachment,
    ) -> Optional[ImageAttachment]:
        if not prompt.strip() or not self.config.image_generation_enabled or not self.config.api_key:
            return None
        ref_bytes, ref_filename, ref_mime = reference_image
        image_ext, _mime_type = self._image_mime_type()
        body, boundary = self._multipart_body(
            {
                "model": self.config.image_model,
                "prompt": truncate_text(prompt, 4000),
                "size": self.config.image_size,
                "quality": self.config.image_quality,
                "n": 1,
                "output_format": image_ext,
            },
            [("image[]", ref_filename, ref_mime, ref_bytes)],
        )
        request = Request(
            "https://api.openai.com/v1/images/edits",
            data=body,
            headers=self._headers(f"multipart/form-data; boundary={boundary}"),
            method="POST",
        )
        try:
            started = time.perf_counter()
            ok = False
            with self._open(request, timeout=self.config.image_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            ok = True
            return self._image_from_response(payload)
        except HTTPError as err:
            self._log_error("OpenAI reference image generation failed: %s", http_error_excerpt(err))
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as err:
            self._log_error("OpenAI reference image generation failed: %s", redact_secrets(err, extra_secrets=[self.config.api_key]))
        finally:
            record_external_call("openai", "image_edit", time.perf_counter() - started, ok=ok)
        return None

    def _generate_image_from_prompt(self, prompt: str) -> Optional[ImageAttachment]:
        if not prompt.strip() or not self.config.image_generation_enabled or not self.config.api_key:
            return None
        image_ext, _mime_type = self._image_mime_type()
        payload: Dict[str, Any] = {
            "model": self.config.image_model,
            "prompt": truncate_text(prompt, 4000),
            "size": self.config.image_size,
            "quality": self.config.image_quality,
            "n": 1,
        }
        if image_ext in {"jpeg", "png", "webp"}:
            payload["output_format"] = image_ext
        try:
            response = self._post_json(
                "https://api.openai.com/v1/images/generations",
                payload,
                self.config.image_timeout_seconds,
            )
            return self._image_from_response(response)
        except HTTPError as err:
            self._log_error("OpenAI image generation failed: %s", http_error_excerpt(err))
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as err:
            self._log_error("OpenAI image generation failed: %s", redact_secrets(err, extra_secrets=[self.config.api_key]))
        return None

    def _post_json(self, url: str, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self._headers("application/json"),
            method="POST",
        )
        started = time.perf_counter()
        ok = False
        try:
            with self._open(request, timeout=timeout) as response:
                parsed = json.loads(response.read().decode("utf-8"))
            ok = True
        finally:
            record_external_call("openai", "post_json", time.perf_counter() - started, ok=ok)
        return parsed if isinstance(parsed, dict) else {}

    def _image_from_response(self, response: Dict[str, Any]) -> Optional[ImageAttachment]:
        image_ext, mime_type = self._image_mime_type()
        items = response.get("data") if isinstance(response, dict) else None
        first = items[0] if isinstance(items, list) and items else {}
        if first.get("b64_json"):
            image_bytes = base64.b64decode(str(first["b64_json"]))
        elif first.get("url"):
            started = time.perf_counter()
            ok = False
            try:
                with self._open(str(first["url"]), timeout=self.config.image_timeout_seconds) as response:
                    image_bytes = response.read(self.config.generated_image_max_bytes + 1)
                ok = True
            finally:
                record_external_call("openai", "generated_image_get", time.perf_counter() - started, ok=ok)
        else:
            return None
        if len(image_bytes) > self.config.generated_image_max_bytes:
            self._log_error("OpenAI generated image ignored: file exceeds configured max size")
            return None
        return image_bytes, f"anba-news.{image_ext}", mime_type

    def _image_mime_type(self) -> tuple[str, str]:
        image_format = self.config.image_format.lower()
        if image_format == "webp":
            return "webp", "image/webp"
        if image_format in {"jpg", "jpeg"}:
            return "jpeg", "image/jpeg"
        return "png", "image/png"

    @staticmethod
    def _reference_image_mime_type(content_type: str, url_path: str) -> tuple[str, str]:
        mime = (content_type or "").split(";", 1)[0].strip().lower()
        if mime in {"image/jpeg", "image/jpg"}:
            return "jpg", "image/jpeg"
        if mime == "image/png":
            return "png", "image/png"
        if mime == "image/webp":
            return "webp", "image/webp"
        path = url_path.lower()
        if path.endswith((".jpg", ".jpeg")):
            return "jpg", "image/jpeg"
        if path.endswith(".webp"):
            return "webp", "image/webp"
        return "png", "image/png"

    def _headers(self, content_type: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": content_type,
            "User-Agent": "anba-excel/1.0",
        }

    @staticmethod
    def _multipart_body(
        fields: Dict[str, Any],
        files: List[tuple[str, str, str, bytes]],
    ) -> tuple[bytes, str]:
        boundary = f"----anba-openai-{secrets.token_hex(16)}"
        chunks: List[bytes] = []
        for name, value in fields.items():
            if value in (None, ""):
                continue
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            )
        for field_name, filename, mime_type, file_bytes in files:
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode("utf-8"),
                    f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"),
                    file_bytes,
                    b"\r\n",
                ]
            )
        chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
        return b"".join(chunks), boundary
