from agent_fabric import Fabric

with Fabric.from_env() as fabric:
    client = fabric.llm.client(sync=True)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "What is the capital of Switzerland"}],
    )
    print(response.choices[0].message.content)