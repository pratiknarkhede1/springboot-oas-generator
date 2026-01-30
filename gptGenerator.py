#!/usr/bin/env python3
"""
End-to-end Spring Boot code generator:
- External OAS → Spring wrapper
- Internal OAS → REST client
- Mapping-driven LLM logic generation
- Safe method-body merge
"""

import os
import re
import yaml
import json
import subprocess
import tempfile
import pathlib
import textwrap
import sys

# =========================
# CONFIG
# =========================

EXTERNAL_OAS = "external.yaml"
INTERNAL_OAS = "internal.yaml"
MAPPING_FILE = "mapping.yaml"

OUTPUT_DIR = "generated-app"
INTERNAL_CLIENT_DIR = "internal-client"

JAVA_VERSION = "21"

BEDROCK_MODEL = "bedrock/nova-lite"
LITELLM_ENDPOINT = "http://localhost:4000/v1/chat/completions"

# =========================
# UTILS
# =========================

def run(cmd):
    print(f"▶ {cmd}")
    subprocess.run(cmd, shell=True, check=True)

def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)

# =========================
# STEP 1 — Generate External Wrapper
# =========================

def generate_external():
    run(f"""
    openapi-generator generate \
      -i {EXTERNAL_OAS} \
      -g spring \
      -o {OUTPUT_DIR} \
      --additional-properties=delegatePattern=true,java21=true
    """)

# =========================
# STEP 2 — Generate Internal REST Client
# =========================

def generate_internal():
    run(f"""
    openapi-generator generate \
      -i {INTERNAL_OAS} \
      -g java \
      -o {INTERNAL_CLIENT_DIR} \
      --additional-properties=library=webclient,useJakartaEe=true
    """)

# =========================
# STEP 3 — Load Mapping
# =========================

def load_mapping():
    return load_yaml(MAPPING_FILE)["endpoints"]

# =========================
# STEP 4 — Find DelegateImpl
# =========================

def find_delegate_impl():
    base = pathlib.Path(OUTPUT_DIR)
    for p in base.rglob("*DelegateImpl.java"):
        return p
    raise Exception("DelegateImpl not found")

# =========================
# STEP 5 — LLM CALL
# =========================

def generate_method_body(prompt):
    payload = {
        "model": BEDROCK_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0
    }

    result = subprocess.run(
        [
            "curl", "-s",
            "-X", "POST",
            LITELLM_ENDPOINT,
            "-H", "Content-Type: application/json",
            "-d", json.dumps(payload)
        ],
        capture_output=True,
        text=True,
        check=True
    )

    content = json.loads(result.stdout)
    return content["choices"][0]["message"]["content"]

# =========================
# STEP 6 — Merge Method Body
# =========================

def merge_logic(java_file, method_name, new_body):
    src = java_file.read_text()

    pattern = re.compile(
        rf"(public .* {method_name}\(.*?\)\s*\{{)(.*?)(\n\s*\}})",
        re.S
    )

    match = pattern.search(src)
    if not match:
        raise Exception(f"Method {method_name} not found")

    merged = (
        match.group(1)
        + "\n"
        + textwrap.indent(new_body.strip(), " " * 8)
        + match.group(3)
    )

    src = src[:match.start()] + merged + src[match.end():]
    java_file.write_text(src)

# =========================
# STEP 7 — MAIN
# =========================

def main():
    print("\n=== STEP 1: External API ===")
    generate_external()

    print("\n=== STEP 2: Internal Client ===")
    generate_internal()

    print("\n=== STEP 3: Mapping ===")
    mapping = load_mapping()

    delegate = find_delegate_impl()
    print(f"Using delegate: {delegate}")

    for name, cfg in mapping.items():
        print(f"\n=== Generating logic for {name} ===")

        prompt = f"""
Generate ONLY the Java method body.

External method:
ResponseEntity<{cfg['external']['response']}> {name}({', '.join(p['type'] + ' ' + p['name'] for p in cfg['external']['params'])})

Internal REST call:
{cfg['internal']['client']}.{cfg['internal']['method']}({', '.join(p['name'] for p in cfg['external']['params'])})

Rules:
- No imports
- No annotations
- Catch WebClientResponseException.NotFound → return ResponseEntity.notFound().build()
- Map internal response to external response
"""

        body = generate_method_body(prompt)
        merge_logic(delegate, name, body)

    print("\n=== DONE ===")
    print("Run: mvn clean verify")

if __name__ == "__main__":
    main()
