# Architecture and compatibility

## Why this document exists

Qwen3.5-0.8B is not a conventional dense decoder-only transformer. Treating it
as one can produce confusing load failures, silently untrained adapter modules,
or invalid memory estimates. CyberLite records the actual checkpoint class and
uses an architecture-aware loading path.

## Checkpoint facts

Verified against `config.json` and a local load of
`Qwen/Qwen3.5-0.8B` (November 2026):

| Field | Value |
|---|---|
| `architectures` | `["Qwen3_5ForConditionalGeneration"]` |
| Top-level `model_type` | `qwen3_5` |
| Text model type | `qwen3_5_text` |
| Text layers | 24 |
| Layer pattern | 18 `linear_attention`, 6 `full_attention` |
| Hidden size | 1024 |
| Attention heads / KV heads | 8 / 2 |
| Head dimension | 256 |
| MLP intermediate size | 3584 |
| Vocabulary | 248,320 (tied embeddings) |
| Max positions (config) | 262,144 |
| MTP layers | 1 |
| Vision tower | 12 layers, hidden 768, output 1024 |
| Total parameters | 852,985,920 |
| Vision parameters | 100,592,896 |
| License | Apache-2.0 (upstream; verify) |

The presence of a vision tower and a `ForConditionalGeneration` class means the
checkpoint is multimodal. CyberLite trains and serves **text only**; images and
videos are outside the current scope.

## Loading path

`cyberlite/training/model.py` and `cyberlite/inference/engine.py` both:

1. load `AutoConfig`;
2. detect `vision_config` or a `ConditionalGeneration` architecture;
3. choose `AutoModelForImageTextToText` for multimodal checkpoints, otherwise
   `AutoModelForCausalLM`;
4. load with an explicit dtype, optional attention implementation, and optional
   bitsandbytes quantization;
5. record the auto class, loaded class, parameter counts, and multimodal flag in
   run metadata.

For Qwen3.5-0.8B the observed loaded class is
`Qwen3_5ForConditionalGeneration`, wrapped by PEFT as
`PeftModelForCausalLM` after LoRA attachment. A text-only forward pass with
`input_ids`, `attention_mask`, and `labels` is valid.

Do **not** assume `AutoModelForCausalLM.from_pretrained("Qwen/Qwen3.5-0.8B")`
works. The text-only `Qwen3_5ForCausalLM` class exists, but the released
checkpoint uses the multimodal wrapper.

## LoRA target modules

The default target set covers both block families:

```text
q_proj, k_proj, v_proj, o_proj          # gated full attention
in_proj_qkv, in_proj_z, in_proj_b, in_proj_a, out_proj   # linear attention
gate_proj, up_proj, down_proj           # MLP
```

Targeting only `q_proj`/`v_proj` would leave most projections untouched. The
pipeline resolves targets against the actual model and fails if a configured
name is missing. `modules_to_save` is unset by default; chat formatting lives in
the tokenizer/template rather than adapter weights.

The vision tower is frozen by default (`model.freeze_vision: true`). This
reduces trainable parameters and avoids spending capacity on an unused modality.
Set it to `false` only for a deliberate multimodal experiment.

## Fill-in-the-middle

The Qwen3.5 tokenizer defines:

```text
<|fim_prefix|> <|fim_suffix|> <|fim_middle|> <|fim_pad|>
```

CyberLite trains with the standard order
`<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>{middle}`. Token
presence does not prove the base checkpoint was trained for FIM; that is an
empirical question. The autocomplete engine therefore:

- uses FIM when the tokens exist and the user requests `mode=fim`;
- can force prefix/instruction completion with `mode=prefix`;
- documents that prefix mode is the fallback when FIM quality is inadequate.

## Optional accelerated kernels

The Qwen3.5 implementation can use `causal-conv1d` and
`flash-linear-attention` on suitable GPUs. Without them, Transformers falls
back to reference PyTorch kernels. The fallback is correct but slower, and it is
the path used by the CPU smoke tests. CyberLite does not install these kernels
by default because availability is platform- and CUDA-version-dependent.

Similarly, `flash_attention_2` is rejected on CPU and requires a compatible GPU
build. The default is `sdpa`.

## Larger control models

Architecture selection is config-driven. To test a larger Qwen3.5 checkpoint or
a conventional text model, change `model.id` and set `model.parameters_b` for
planning. The loader will select the correct auto class. Validate that the
tokenizer has the expected chat template and, for FIM experiments, the control
tokens before launching a run.

## Minimum compatibility checks

Before a training run:

```bash
python - <<'PY'
from transformers import AutoConfig, AutoTokenizer
model_id = "Qwen/Qwen3.5-0.8B"
config = AutoConfig.from_pretrained(model_id)
tokenizer = AutoTokenizer.from_pretrained(model_id)
print(config.architectures, config.model_type)
print("vision:", hasattr(config, "vision_config"))
print("fim:", tokenizer.convert_tokens_to_ids("<|fim_middle|>"))
PY
```

The repository's integration test does the same through the package:

```bash
CYBERLITE_RUN_INTEGRATION=1 pytest tests/integration -q
```

Integration tests download weights and are skipped by default.
