import os

from zknowbase_client import ZKnowbaseClient


client = ZKnowbaseClient(
    base_url=os.environ.get("ZKNOWBASE_URL", "http://localhost:8000"),
    api_key=os.environ["ZKNOWBASE_API_KEY"],
)

# Agent/tool retrieval without generation.
contexts = client.search("What is the employee leave approval workflow?", top_k=5)

# Grounded answer for a zworkforce task/agent.
answer = client.ask("Summarize the employee leave approval workflow and cite the policy.")
print(answer["answer"])
for source in answer["sources"]:
    print(source["document_name"], source["score"])
