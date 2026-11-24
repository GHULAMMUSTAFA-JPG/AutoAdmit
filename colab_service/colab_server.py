"""Standalone Google Colab T4 GPU OpenAI-Compatible Server for 4-bit NF4 Qwen/Qwen2.5-7B-Instruct (~5.5 GB VRAM)."""

import gc
import hmac
import inspect
import os
import time
import uuid
from typing import Any
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
MAX_MESSAGES = 32
MAX_TOTAL_CHARS = 60_000
MAX_NEW_TOKENS_CAP = 1024


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = MODEL_ID
    messages: list[ChatMessage]
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=512, ge=1, le=MAX_NEW_TOKENS_CAP)
    response_format: dict[str, Any] | None = None


class QwenModelRegistry:
    """Loads Qwen/Qwen2.5-7B-Instruct in 4-bit NF4 quantization onto Colab T4 GPU (~5.5 GB VRAM)."""

    def __init__(self) -> None:
        self.model_id: str = MODEL_ID
        self.tokenizer: Any = None
        self.model: Any = None
        self.generate_fn: Any = None  # Injectable callable for offline CPU pytest
        self.device: str = "cpu"
        self.vram_allocated_mb: float = 0.0
        self.vram_total_mb: float = 0.0

    def load_qwen_4bit(self) -> None:
        """Loads Qwen/Qwen2.5-7B-Instruct in 4-bit NF4 onto GPU 0 cleanly inside Colab T4 15GB VRAM / 12.7GB RAM."""
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        use_cuda = torch.cuda.is_available()
        self.device = torch.cuda.get_device_name(0) if use_cuda else "cpu"
        target_dtype = torch.float16 if use_cuda else torch.float32

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )

        # Use modern `dtype` arg when supported by transformers, else fallback to `torch_dtype`
        from_pretrained_params = inspect.signature(AutoModelForCausalLM.from_pretrained).parameters
        dtype_kw = {"dtype": target_dtype} if "dtype" in from_pretrained_params else {"torch_dtype": target_dtype}

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        load_kwargs: dict[str, Any] = {
            "low_cpu_mem_usage": True,
            **dtype_kw,
        }
        if use_cuda:
            load_kwargs["quantization_config"] = bnb_config
            # Pin strictly to GPU 0 so accelerate never spills layers to Colab's 12.7 GB CPU RAM
            load_kwargs["device_map"] = {"": 0}

        self.model = AutoModelForCausalLM.from_pretrained(self.model_id, **load_kwargs)
        self.model.eval()
        gc.collect()
        if use_cuda:
            torch.cuda.empty_cache()
            self.vram_allocated_mb = round(torch.cuda.memory_allocated() / (1024 * 1024), 1)
            self.vram_total_mb = round(torch.cuda.get_device_properties(0).total_memory / (1024 * 1024), 1)

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 512,
        json_mode: bool = False,
    ) -> str:
        if len(messages) > MAX_MESSAGES:
            raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Too many messages.")
        total_chars = sum(len(m.content) for m in messages)
        if total_chars > MAX_TOTAL_CHARS:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Prompt too large ({total_chars} chars). Max allowed is {MAX_TOTAL_CHARS}.",
            )

        msg_dicts = [{"role": m.role, "content": m.content} for m in messages]
        if json_mode:
            msg_dicts.insert(0, {"role": "system", "content": "Respond ONLY with valid JSON. No markdown fences or extra prose."})

        if self.generate_fn is not None:
            return str(self.generate_fn(msg_dicts, temperature, max_tokens))

        if self.model is None or self.tokenizer is None:
            raise HTTPException(status_code=503, detail=f"Model '{self.model_id}' is not loaded.")

        import torch
        model_device = next(self.model.parameters()).device
        prompt_text = self.tokenizer.apply_chat_template(msg_dicts, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(prompt_text, return_tensors="pt").to(model_device)
        do_sample = temperature > 0.0
        gen_kwargs: dict[str, Any] = {
            "max_new_tokens": min(max_tokens, MAX_NEW_TOKENS_CAP),
            "do_sample": do_sample,
        }
        if do_sample:
            gen_kwargs["temperature"] = temperature

        with torch.no_grad():
            output_ids = self.model.generate(**inputs, **gen_kwargs)
        new_tokens = output_ids[0][inputs["input_ids"].shape[1]:]
        text = self.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return text


def create_colab_app(registry: QwenModelRegistry | None = None, api_key: str | None = None) -> FastAPI:
    reg = registry or QwenModelRegistry()
    fixed_key = api_key

    app = FastAPI(title="AutoAdmit Colab T4 Qwen2.5-7B Server", version="2.1.0")
    app.state.registry = reg

    @app.middleware("http")
    async def api_key_middleware(request: Request, call_next):
        provided = request.headers.get("X-API-Key", "")
        expected = fixed_key if fixed_key is not None else os.environ.get("COLAB_API_KEY", "")
        if not expected or not provided or not hmac.compare_digest(provided, expected):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing or invalid X-API-Key header."},
            )
        return await call_next(request)

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "gpu_device": reg.device,
            "vram_allocated_mb": reg.vram_allocated_mb,
            "vram_total_mb": reg.vram_total_mb,
            "model": reg.model_id,
            "loaded": (reg.model is not None or reg.generate_fn is not None),
        }

    @app.post("/v1/chat/completions")
    def chat_completions(body: ChatCompletionRequest):
        t0 = time.perf_counter()
        json_mode = bool(body.response_format and body.response_format.get("type") == "json_object")
        content = reg.chat_complete(
            body.messages,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            json_mode=json_mode,
        )
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": reg.model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "latency_ms": latency_ms,
        }

    return app


app = create_colab_app()
