
import os
import json
from typing import TypedDict, List, Dict, Any
from pydantic import BaseModel, Field
from litellm import completion
from langgraph.graph import StateGraph, START, END

# --- 1. Configuration ---
# Update this to your specific LiteLLM endpoint/model name
MODEL_NAME = "anthropic/claude-3-5-sonnet-20240620" 

# --- 2. Schema Definitions ---

class GeneratedFile(BaseModel):
    path: str = Field(description="The file path, e.g., src/main/java/com/example/api/dto/UserDTO.java")
    content: str = Field(description="The full code content of the file")
    language: str = Field(description="java, xml, or yaml")

class GenerationPlan(BaseModel):
    steps: List[Dict[str, str]] = Field(description="List of logical steps for generation")
    package_name: str = Field(description="The base package name, e.g., com.example.api", default="com.example.api")
    dtos: List[str] = Field(description="Names of DTOs to be generated")
    services: List[str] = Field(description="Names of Service classes")
    controllers: List[str] = Field(description="Names of Controller classes")

class AgentState(TypedDict):
    external_oas: str
    internal_oas: str
    mapping_instructions: str
    plan: GenerationPlan
    files: List[GeneratedFile]
    current_layer: str

# --- 3. System Prompts ---

SYSTEM_PROMPT = """
You are a Senior Java Architect and Developer specializing in Spring Boot 3.4+ and Java 21.
Your task is to generate a PRODUCTION-READY, RUNNABLE Spring Boot application.
Key technical requirements:
1. Use Java 21 (Record types, pattern matching where applicable).
2. Spring Boot 3.4+ with 'spring-boot-starter-web' and 'spring-boot-starter-validation'.
3. Use Lombok (@Data, @Builder, @AllArgsConstructor) to reduce boilerplate.
4. Use Spring's 'RestClient' (introduced in SB 3.2) for internal API calls.
5. Strict Package Structure: 
   - [base].MainApplication.java
   - [base].controller.*
   - [base].service.*
   - [base].model.dto.* (External & Internal)
6. Ensure all @Service and @RestController beans are correctly annotated for Component Scanning.
7. Provide a complete pom.xml with all necessary dependencies.
"""

# --- 4. Node Implementations ---

def call_llm(messages: List[Dict], response_schema: Any = None):
    """Utility to call LiteLLM with JSON mode support."""
    # Note: response_format is used if the provider/LiteLLM supports it, 
    # otherwise we parse the string. Claude via LiteLLM supports JSON.
    response = completion(
        model=MODEL_NAME,
        messages=messages,
        response_format={ "type": "json_object" } if response_schema else None
    )
    content = response.choices[0].message.content
    if response_schema:
        return json.loads(content)
    return content

def planner_node(state: AgentState):
    """Analyzes requirements and creates a construction plan."""
    print("--- STEP: PLANNING ---")
    prompt = f"""
    Analyze the following specs and create a Generation Plan.
    External OAS: {state['external_oas']}
    Internal OAS: {state['internal_oas']}
    Mapping: {state['mapping_instructions']}
    
    The plan must identify all DTOs (Request/Response), the Service logic required for mapping, 
    and the Controller endpoints.
    Return JSON matching the GenerationPlan schema.
    """
    
    plan_data = call_llm([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ], response_schema=True)
    
    return {"plan": GenerationPlan(**plan_data)}

def layer_generator_node(state: AgentState):
    """Generic node to generate a specific architectural layer."""
    layer = state['current_layer']
    print(f"--- STEP: GENERATING {layer} ---")
    
    # We include the previous files in context to ensure imports and references are consistent
    existing_files_summary = "\n".join([f"File: {f.path}" for f in state['files']])
    
    prompt = f"""
    Generate the {layer} layer files based on the plan.
    Current Plan: {state['plan'].json()}
    Mapping Instructions: {state['mapping_instructions']}
    
    Files already generated:
    {existing_files_summary}
    
    REQUIREMENTS for {layer}:
    - If MODELS: Generate Records/Classes for both External and Internal APIs.
    - If SERVICES: Implement RestClient logic calling Internal endpoints.
    - If CONTROLLERS: Expose External endpoints and call Services.
    - If CONFIG: Generate pom.xml, application.yml, and the Main Application class.
    
    Return a JSON object with a 'files' key containing a list of {path, content, language}.
    """
    
    response_data = call_llm([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ], response_schema=True)
    
    new_files_data = response_data.get('files', [])
    new_files = [GeneratedFile(**f) for f in new_files_data]
    
    return {"files": state['files'] + new_files}

# --- 5. Graph Construction ---

def create_spring_gen_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("planner", planner_node)
    
    def set_layer(layer_name):
        return lambda state: layer_generator_node({**state, "current_layer": layer_name})

    workflow.add_node("generate_models", set_layer("MODELS"))
    workflow.add_node("generate_services", set_layer("SERVICES"))
    workflow.add_node("generate_controllers", set_layer("CONTROLLERS"))
    workflow.add_node("generate_config", set_layer("CONFIG"))

    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "generate_models")
    workflow.add_edge("generate_models", "generate_services")
    workflow.add_edge("generate_services", "generate_controllers")
    workflow.add_edge("generate_controllers", "generate_config")
    workflow.add_edge("generate_config", END)

    return workflow.compile()

# --- 6. Utility: Save to Disk ---

def save_project(files: List[GeneratedFile], output_dir: str = "generated_spring_app"):
    """Saves the generated code into a proper directory structure."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    for file in files:
        full_path = os.path.join(output_dir, file.path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(file.content)
    print(f"\nSUCCESS: Project saved to {output_dir}")

# --- 7. Execution ---

if __name__ == "__main__":
    inputs = {
        "external_oas": """
            paths:
              /v1/orders:
                get:
                  responses:
                    '200':
                      content:
                        application/json:
                          schema:
                            type: array
                            items: { $ref: '#/components/schemas/Order' }
        """,
        "internal_oas": """
            paths:
              /api/internal/legacy-orders:
                get:
                  responses:
                    '200':
                      description: Returns legacy order objects
        """,
        "mapping_instructions": "Map /v1/orders to /api/internal/legacy-orders. Map legacy field 'order_id' to 'id'.",
        "files": [],
        "plan": None,
        "current_layer": ""
    }

    print("Starting Agentic Generation Process...")
    app = create_spring_gen_graph()
    final_state = app.invoke(inputs)

    # Save to disk
    save_project(final_state['files'])
