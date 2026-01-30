#!/usr/bin/env python3
"""
End-to-end Spring Boot code generator:
- External OAS → Spring wrapper
- Internal OAS → REST client
- Mapping-driven LLM logic generation
- Safe method-body merge
External.ymal:

paths:
  /orders/{id}:
    get:
      operationId: getOrder
      responses:
        "200":
          description: ok
Internal:
paths:
  /internal/orders/{id}:
    get:
      operationId: getInternalOrder

mapping.yaml

endpoints:
  getOrder:
    external:
      response: OrderResponse
      params:
        - name: id
          type: String
    internal:
      client: internalOrdersApi
      method: getInternalOrder

"""
#!/usr/bin/env python3

import subprocess
import yaml
import json
import re
import pathlib
import textwrap
import urllib.request

# ================= CONFIG =================

GENERATOR_VERSION = "7.6.0"
GENERATOR_JAR = f"openapi-generator-cli-{GENERATOR_VERSION}.jar"
GENERATOR_URL = f"https://repo1.maven.org/maven2/org/openapitools/openapi-generator-cli/{GENERATOR_VERSION}/{GENERATOR_JAR}"

EXTERNAL_OAS = "external.yaml"
INTERNAL_OAS = "internal.yaml"
MAPPING_FILE = "mapping.yaml"
APP_DIR = "app"

LITELLM_URL = "http://localhost:4000/v1/chat/completions"
MODEL = "bedrock/nova-lite"

# ================= UTILS =================

def run(cmd):
    print(f"\n▶ {cmd}")
    subprocess.run(cmd, shell=True, check=True)

def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)

def ensure_generator():
    if not pathlib.Path(GENERATOR_JAR).exists():
        print("⬇ Downloading OpenAPI Generator JAR...")
        urllib.request.urlretrieve(GENERATOR_URL, GENERATOR_JAR)

# ================= STEP 1: SPRING APP =================

def generate_spring():
    run(f"""
java -jar {GENERATOR_JAR} generate \
  -i {EXTERNAL_OAS} \
  -g spring \
  -o {APP_DIR} \
  --additional-properties=delegatePattern=true,java21=true,interfaceOnly=false
""")

# ================= STEP 2: INTERNAL CLIENT =================

def generate_internal_client():
    run(f"""
java -jar {GENERATOR_JAR} generate \
  -i {INTERNAL_OAS} \
  -g java \
  -o /tmp/internal \
  --additional-properties=library=webclient,useJakartaEe=true
""")

    run(f"cp -r /tmp/internal/src/main/java/* {APP_DIR}/src/main/java/")

# ================= STEP 3: CONFIG =================

def add_webclient_config():
    cfg = pathlib.Path(f"{APP_DIR}/src/main/java/config/WebClientConfig.java")
    cfg.parent.mkdir(parents=True, exist_ok=True)

    cfg.write_text("""
package config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfig {

    @Bean
    public WebClient webClient() {
        return WebClient.builder().build();
    }
}
""")

# ================= STEP 4: LLM =================

def llm(prompt):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0
    }

    res = subprocess.run(
        ["curl", "-s", "-X", "POST", LITELLM_URL,
         "-H", "Content-Type: application/json",
         "-d", json.dumps(payload)],
        capture_output=True,
        text=True
    )

    return json.loads(res.stdout)["choices"][0]["message"]["content"]

# ================= STEP 5: MERGE =================

def merge_method(java_file, method, body):
    src = java_file.read_text()

    pattern = re.compile(
        rf"(public .* {method}\(.*?\)\s*\{{)(.*?)(\n\s*\}})",
        re.S
    )

    m = pattern.search(src)
    if not m:
        raise RuntimeError(f"{method} not found")

    new_src = (
        src[:m.start()]
        + m.group(1)
        + "\n"
        + textwrap.indent(body.strip(), " " * 8)
        + m.group(3)
        + src[m.end():]
    )

    java_file.write_text(new_src)

# ================= MAIN =================

def main():
    ensure_generator()

    generate_spring()
    generate_internal_client()
    add_webclient_config()

    mapping = load_yaml(MAPPING_FILE)["endpoints"]

    delegate = next(pathlib.Path(APP_DIR).rglob("*DelegateImpl.java"))

    for method, cfg in mapping.items():
        prompt = f"""
Generate Java method body ONLY.

External:
ResponseEntity<{cfg['external']['response']}> {method}(String id)

Internal:
{cfg['internal']['client']}.{cfg['internal']['method']}(id)

Rules:
- Must return ResponseEntity
- Catch WebClientResponseException.NotFound
- No imports, annotations, class definitions
"""

        body = llm(prompt)
        merge_method(delegate, method, body)

    print("\n✅ DONE")
    print("Run:")
    print(f"cd {APP_DIR} && mvn clean spring-boot:run")

if __name__ == "__main__":
    main()

