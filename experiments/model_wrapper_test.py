from research_landscape.llm.local_model import LocalLLM

llm = LocalLLM()

messages = [
    {"role": "user", "content": "What is gradient descent? Answer in one sentence."}
]

response = llm.generate(messages)

print(response)