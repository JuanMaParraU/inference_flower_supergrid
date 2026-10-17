"""ClientApp: answer a query by running a locally-served Ollama model.

Each SuperNode on the grid runs this app and does its own local inference;
no model weights or data ever leave the node.
"""

import ollama
from flwr.app import ConfigRecord, Context, Message, RecordDict
from flwr.clientapp import ClientApp

app = ClientApp()


@app.query()
def query(msg: Message, context: Context) -> Message:
    model = context.run_config["model"]
    prompt = msg.content["config"]["prompt"]

    result = ollama.generate(model=model, prompt=prompt)

    content = RecordDict({"config": ConfigRecord({"response": result["response"]})})
    return Message(content=content, reply_to=msg)
