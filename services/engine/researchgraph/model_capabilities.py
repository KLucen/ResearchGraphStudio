"""Model-specific limits from the configured endpoint, never inferred from an alias."""

from typing import Any, Literal

from pydantic import Field, model_validator

from researchgraph.core import StrictModel


class ModelCapabilities(StrictModel):
    max_output_tokens: int | None = Field(default=None, ge=128, le=2_000_000)
    context_window: int | None = Field(default=None, ge=1024, le=10_000_000)
    # ``text`` is the conservative default for OpenAI-compatible chat APIs. A
    # provider must explicitly advertise ``pdf`` or ``image`` before a model
    # document task is allowed to send a file/visual payload. This prevents the
    # new importer from silently falling back to the legacy local parser.
    document_input: Literal["text", "pdf", "image"] = "text"
    multimodal: bool = False
    # File transport is deliberately explicit.  A model advertising PDF/image
    # input without a known transport must not receive a file by accident.
    document_transport: Literal["none", "chat_file", "chat_images"] = "none"
    source: str = "provider_default"

    @model_validator(mode="after")
    def validate_visual_transport(self) -> "ModelCapabilities":
        if self.document_transport == "chat_images" and (
            self.document_input != "image" or not self.multimodal
        ):
            raise ValueError("PDF 页面图片传输需要声明图片输入和多模态能力")
        return self


def parse_capabilities(value: dict[str, Any]) -> ModelCapabilities:
    containers = [value]
    for key in ("capabilities", "limits", "top_provider"):
        if isinstance(value.get(key), dict):
            containers.append(value[key])

    def number(names: tuple[str, ...], low: int, high: int) -> int | None:
        for container in containers:
            for name in names:
                result = container.get(name)
                if type(result) is int and low <= result <= high:
                    return result
        return None

    output = number(
        ("max_output_tokens", "max_completion_tokens", "output_token_limit"), 128, 2_000_000
    )
    context = number(("context_window", "context_length", "max_context_tokens"), 1024, 10_000_000)

    document_input: Literal["text", "pdf", "image"] = "text"
    multimodal = False
    document_transport: Literal["none", "chat_file", "chat_images"] = "none"
    discovered_document = False
    for container in containers:
        raw_input = container.get("document_input")
        if raw_input in {"text", "pdf", "image"}:
            document_input = raw_input
            discovered_document = True
        raw_transport = container.get("document_transport")
        # Image input metadata alone does not authorize local PDF rendering or
        # select a new transport. chat_images remains an explicit user choice.
        if raw_transport in {"none", "chat_file"}:
            document_transport = raw_transport
            discovered_document = True
        raw_modalities = container.get("input_modalities")
        if isinstance(raw_modalities, list) and all(
            isinstance(item, str) for item in raw_modalities
        ):
            values = set(raw_modalities)
            if "image" in values:
                document_input, multimodal = "image", True
                discovered_document = True
            elif "pdf" in values and document_input == "text":
                document_input = "pdf"
                discovered_document = True
        if container.get("multimodal") is True:
            multimodal = True
            if document_input == "text":
                document_input = "image"
            discovered_document = True
        if container.get("file_input") is True and document_transport == "none":
            document_transport = "chat_file"
            discovered_document = True
    return ModelCapabilities(
        max_output_tokens=output,
        context_window=context,
        document_input=document_input,
        multimodal=multimodal,
        document_transport=document_transport,
        source=(
            "endpoint_metadata" if output or context or discovered_document else "provider_default"
        ),
    )
