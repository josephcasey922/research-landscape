import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from research_landscape.processing.methodology_extraction import parse_extraction

model_name = "Qwen/Qwen2.5-1.5B-Instruct"

tokenizer = AutoTokenizer.from_pretrained(model_name)

model = AutoModelForCausalLM.from_pretrained(
    model_name,
    dtype=torch.float16,
    device_map="auto"
)

passage = """
Experiments on two machine translation tasks show these models
to be superior in quality while being more parallelizable and
requiring significantly less time to train.
"""

system_prompt = """
You extract research methodology information from scientific text.

Return only a valid JSON object with these four keys:
method, evaluation, data, limitations.

Definitions:
- method: A specific algorithm, technique, model architecture, or
  research procedure. Do not use generic words like "experiments".
- evaluation: How the researchers tested or compared their approach.
  Describe the procedure, not the conclusion or results.
- data: Named datasets, data sources, or experimental inputs.
  Do not include performance claims or model characteristics.
- limitations: Explicitly stated weaknesses or constraints.

Rules:
- Use null when the passage does not provide the information.
- Do not infer details from general knowledge.
- Do not force every field to contain a value.
- Do not include text outside the JSON object.
"""

messages = [
    {
        "role": "system",
        "content": system_prompt
    },
    {
        "role": "user",
        "content": (
            "We trained a convolutional neural network on the "
            "CIFAR-10 dataset and evaluated its classification "
            "accuracy on a held-out test set."
        )
    },
    {
        "role": "assistant",
        "content": """{
            "method": "convolutional neural network",
            "evaluation": "classification accuracy on a held-out test set",
            "data": "CIFAR-10",
            "limitations": null
        }"""
    },
    {
        "role": "user",
        "content": passage
    }
]

inputs = tokenizer.apply_chat_template(
    messages,
    add_generation_prompt=True,
    return_tensors="pt",
    return_dict=True
).to(model.device)

with torch.inference_mode():
    outputs = model(**inputs)

logits = outputs.logits
print("Logits shape:", logits.shape)

next_token_logits = logits[0, -1, :]

probabilities = torch.softmax(next_token_logits, dim=-1)

top_probs, top_ids = torch.topk(probabilities, k=5)

for token_id, probability in zip(top_ids, top_probs):
    token = tokenizer.decode([token_id.item()])
    print(repr(token), round(probability.item(), 4))

model.eval()

with torch.inference_mode():
    outputs = model.generate(
        **inputs,
        max_new_tokens=250,
        do_sample=False
    )

input_length = inputs["input_ids"].shape[-1]
new_tokens = outputs[0][input_length:]

response = tokenizer.decode(
    new_tokens,
    skip_special_tokens=True
)

print(response)
print(
    "Peak allocated GPU memory:",
    round(torch.cuda.max_memory_allocated() / 1024**3, 2),
    "GB"
)

extraction = parse_extraction(response)
print("Parsed extraction:", extraction)