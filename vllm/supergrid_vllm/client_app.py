"""ClientApp: answer a query using a locally-served vLLM model.

Each SuperNode runs its own vLLM OpenAI-compatible server (`vllm serve <model>`)
and this app calls it on localhost; no model weights or data leave the node.
"""

from flwr.app import ConfigRecord, Context, Message, RecordDict
from flwr.clientapp import ClientApp
from openai import OpenAI

app = ClientApp()


@app.query()
def query(msg: Message, context: Context) -> Message:
    model = context.run_config["model"]
    base_url = context.run_config["vllm-url"]
    prompt = msg.content["config"]["prompt"]

    client = OpenAI(base_url=base_url, api_key="EMPTY")
    result = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=int(context.run_config["max-tokens"]),
    )

    content = RecordDict(
        {"config": ConfigRecord({"response": result.choices[0].message.content})}
    )
    return Message(content=content, reply_to=msg)
