import boto3
import json

# Initialize Bedrock Agent Runtime client
client = boto3.client("bedrock-agent-runtime", region_name="us-east-1")

AGENT_ID = "your-agent-id"
AGENT_ALIAS_ID = "your-agent-alias-id"

def invoke_agent(wsdl_content: str):
    response = client.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId="wsdl-to-oas-session",
        inputText=f"Convert the following WSDL into OpenAPI 3.0 JSON:\n\n{wsdl_content}"
    )
    
    # Collect streaming output
    output_text = ""
    for event in response["completion"]:
        if "chunk" in event:
            output_text += event["chunk"]["bytes"].decode("utf-8")
    
    return output_text

def get_complete_oas(wsdl_content: str):
    raw_output = invoke_agent(wsdl_content)
    
    # Ensure JSON is complete
    while raw_output.count("{") > raw_output.count("}"):
        continuation = invoke_agent("continue JSON")
        raw_output += continuation
    
    # Validate JSON
    try:
        spec = json.loads(raw_output)
    except json.JSONDecodeError as e:
        print("❌ JSON parse failed:", e)
        print("Partial output:\n", raw_output[:500])
        raise
    
    return spec

if __name__ == "__main__":
    with open("example.wsdl", "r") as f:
        wsdl_content = f.read()
    
    oas = get_complete_oas(wsdl_content)
    
    with open("oas3.json", "w") as f:
        json.dump(oas, f, indent=2)
    
    print("✅ OpenAPI 3.0 spec generated: oas3.json")


You are a converter service.

Input: A WSDL specification.
Output: A complete OpenAPI 3.0 specification in **valid JSON** format, ready to use.

Rules:
- Respond ONLY with a single JSON object (no explanations, no markdown, no comments).
- Always produce the full specification in one response if possible.
- If response is too large, continue JSON exactly where it left off, until the object closes properly.
- Always follow company API standards from the attached Knowledge Base.