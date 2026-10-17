"""ServerApp: fan a prompt out to every connected SuperNode on the grid and print replies."""

from flwr.app import ConfigRecord, Context, Message, MessageType, RecordDict
from flwr.serverapp import Grid, ServerApp

app = ServerApp()


@app.main()
def main(grid: Grid, context: Context) -> None:
    prompt = context.run_config["prompt"]

    node_ids = list(grid.get_node_ids())
    print(f"Connected SuperNodes: {node_ids}")

    messages = [
        Message(
            content=RecordDict({"config": ConfigRecord({"prompt": prompt})}),
            message_type=MessageType.QUERY,
            dst_node_id=node_id,
            group_id="0",
        )
        for node_id in node_ids
    ]

    for reply in grid.send_and_receive(messages):
        if reply.has_error():
            print(f"Node {reply.metadata.src_node_id} failed: {reply.error}")
            continue
        response = reply.content["config"]["response"]
        print(f"\n--- Node {reply.metadata.src_node_id} ---\n{response}")
