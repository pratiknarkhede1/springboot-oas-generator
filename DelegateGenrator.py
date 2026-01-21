#!/usr/bin/env python3
"""
Complete Spring Boot Delegate Auto-Generation System
Generates business logic for Spring Boot delegates by mapping external to internal APIs
"""

import yaml
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import litellm


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class Parameter:
    name: str
    location: str  # path, query, header, body
    required: bool
    type: str
    description: str = ""


@dataclass
class Endpoint:
    path: str
    method: str
    operation_id: str
    parameters: List[Parameter]
    request_body: Optional[Dict[str, Any]]
    response_type: Optional[str]
    summary: str
    description: str
    tag: str = "default"


@dataclass
class EndpointMapping:
    external_endpoint: Endpoint
    internal_endpoint: Endpoint
    param_mapping: Dict[str, str]


# ============================================================================
# OAS PARSER
# ============================================================================

class OASParser:
    """Parse OpenAPI Specification and extract endpoint details"""
    
    def __init__(self, spec_path: str):
        self.spec_path = Path(spec_path)
        with open(spec_path, 'r') as f:
            if spec_path.endswith(('.yaml', '.yml')):
                self.spec = yaml.safe_load(f)
            else:
                self.spec = json.load(f)
    
    def parse_endpoints(self) -> List[Endpoint]:
        """Extract all endpoints from OAS"""
        endpoints = []
        paths = self.spec.get('paths', {})
        
        for path, methods in paths.items():
            for method, details in methods.items():
                if method.lower() not in ['get', 'post', 'put', 'delete', 'patch']:
                    continue
                
                # Parse parameters
                parameters = self._parse_parameters(details.get('parameters', []))
                
                # Parse request body
                request_body = details.get('requestBody')
                if request_body:
                    parameters.append(Parameter(
                        name="body",
                        location="body",
                        required=request_body.get('required', False),
                        type=self._extract_schema_type(request_body),
                        description="Request body"
                    ))
                
                # Parse response type
                response_type = self._extract_response_type(details.get('responses', {}))
                
                # Get tag
                tags = details.get('tags', ['default'])
                tag = tags[0] if tags else 'default'
                
                endpoints.append(Endpoint(
                    path=path,
                    method=method.upper(),
                    operation_id=details.get('operationId', self._generate_operation_id(method, path)),
                    parameters=parameters,
                    request_body=request_body,
                    response_type=response_type,
                    summary=details.get('summary', ''),
                    description=details.get('description', ''),
                    tag=tag
                ))
        
        return endpoints
    
    def _parse_parameters(self, params: List[Dict]) -> List[Parameter]:
        """Parse parameter definitions"""
        parsed = []
        for p in params:
            parsed.append(Parameter(
                name=p.get('name', 'unknown'),
                location=p.get('in', 'query'),
                required=p.get('required', False),
                type=p.get('schema', {}).get('type', 'string'),
                description=p.get('description', '')
            ))
        return parsed
    
    def _extract_schema_type(self, request_body: Dict) -> str:
        """Extract type from request body schema"""
        content = request_body.get('content', {})
        json_content = content.get('application/json', {})
        schema = json_content.get('schema', {})
        
        if '$ref' in schema:
            return schema['$ref'].split('/')[-1]
        return schema.get('type', 'Object')
    
    def _extract_response_type(self, responses: Dict) -> Optional[str]:
        """Extract response type from 200/201 responses"""
        for status in ['200', '201']:
            if status in responses:
                content = responses[status].get('content', {})
                json_content = content.get('application/json', {})
                schema = json_content.get('schema', {})
                
                if '$ref' in schema:
                    return schema['$ref'].split('/')[-1]
                elif schema.get('type'):
                    return schema.get('type')
        
        return None
    
    def _generate_operation_id(self, method: str, path: str) -> str:
        """Generate operation ID from method and path"""
        path_parts = [p for p in path.split('/') if p and not p.startswith('{')]
        return method.lower() + ''.join(p.capitalize() for p in path_parts)
    
    def get_base_path(self) -> str:
        """Extract base path from servers"""
        servers = self.spec.get('servers', [])
        if servers:
            return servers[0].get('url', '')
        return ''


# ============================================================================
# ENDPOINT MAPPER
# ============================================================================

class EndpointMapper:
    """Map external endpoints to internal endpoints"""
    
    def __init__(self, mapping_file: Optional[str] = None):
        self.manual_mappings = {}
        if mapping_file and Path(mapping_file).exists():
            with open(mapping_file, 'r') as f:
                data = yaml.safe_load(f)
                self.manual_mappings = {
                    m['external_operation_id']: m
                    for m in data.get('mappings', [])
                }
    
    def map_endpoints(
        self,
        external_endpoints: List[Endpoint],
        internal_endpoints: List[Endpoint]
    ) -> List[EndpointMapping]:
        """Create mappings between external and internal endpoints"""
        mappings = []
        
        for ext_ep in external_endpoints:
            # Check manual mapping first
            if ext_ep.operation_id in self.manual_mappings:
                manual = self.manual_mappings[ext_ep.operation_id]
                int_ep = self._find_endpoint_by_operation_id(
                    internal_endpoints,
                    manual['internal_operation_id']
                )
                if int_ep:
                    mappings.append(EndpointMapping(
                        external_endpoint=ext_ep,
                        internal_endpoint=int_ep,
                        param_mapping=manual.get('param_mapping', {})
                    ))
                continue
            
            # Auto-map by operation ID similarity
            int_ep = self._find_best_match(ext_ep, internal_endpoints)
            if int_ep:
                param_mapping = self._auto_map_parameters(ext_ep, int_ep)
                mappings.append(EndpointMapping(
                    external_endpoint=ext_ep,
                    internal_endpoint=int_ep,
                    param_mapping=param_mapping
                ))
        
        return mappings
    
    def _find_endpoint_by_operation_id(
        self,
        endpoints: List[Endpoint],
        operation_id: str
    ) -> Optional[Endpoint]:
        """Find endpoint by operation ID"""
        for ep in endpoints:
            if ep.operation_id == operation_id:
                return ep
        return None
    
    def _find_best_match(
        self,
        external: Endpoint,
        internal_endpoints: List[Endpoint]
    ) -> Optional[Endpoint]:
        """Find best matching internal endpoint"""
        # First try exact operation ID match
        for int_ep in internal_endpoints:
            if int_ep.operation_id.lower() == external.operation_id.lower():
                return int_ep
        
        # Try method + similar path
        for int_ep in internal_endpoints:
            if int_ep.method == external.method:
                ext_parts = set(external.path.lower().split('/'))
                int_parts = set(int_ep.path.lower().split('/'))
                if ext_parts & int_parts:  # Has common parts
                    return int_ep
        
        return None
    
    def _auto_map_parameters(self, ext_ep: Endpoint, int_ep: Endpoint) -> Dict[str, str]:
        """Automatically map parameters by name similarity"""
        mapping = {}
        
        ext_params = {p.name.lower(): p.name for p in ext_ep.parameters}
        int_params = {p.name.lower(): p.name for p in int_ep.parameters}
        
        for ext_lower, ext_name in ext_params.items():
            # Exact match
            if ext_lower in int_params:
                mapping[ext_name] = int_params[ext_lower]
                continue
            
            # Try common variations (userId -> id, etc.)
            for int_lower, int_name in int_params.items():
                if ext_lower.endswith(int_lower) or int_lower.endswith(ext_lower):
                    mapping[ext_name] = int_name
                    break
        
        return mapping


# ============================================================================
# CODE GENERATOR (LLM-based)
# ============================================================================

class DelegateCodeGenerator:
    """Generate delegate method implementations using LLM"""
    
    def __init__(self, model: str = "bedrock/amazon.nova-lite-v1:0"):
        self.model = model
        litellm.set_verbose = False
    
    def generate_method_body(
        self,
        mapping: EndpointMapping,
        internal_base_url: str
    ) -> str:
        """Generate complete method body"""
        
        prompt = self._build_prompt(mapping, internal_base_url)
        
        try:
            response = litellm.completion(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert Spring Boot developer. Generate clean, production-ready Java code.
Requirements:
- Use WebClient for REST calls
- Handle 404 errors by returning ResponseEntity.notFound().build()
- Map response types correctly
- Include proper logging
- Return only the method body (no signature, no class wrapper)
- Use Java 17+ features"""
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.2,
                max_tokens=2000
            )
            
            code = response.choices[0].message.content
            return self._clean_generated_code(code)
            
        except Exception as e:
            print(f"⚠️  LLM generation failed: {e}")
            return self._generate_fallback(mapping)
    
    def _build_prompt(self, mapping: EndpointMapping, internal_base_url: str) -> str:
        """Build detailed prompt for LLM"""
        
        ext = mapping.external_endpoint
        internal = mapping.internal_endpoint
        
        # Build parameter list
        param_list = []
        for p in ext.parameters:
            if p.location == 'path':
                param_list.append(f"{p.type} {p.name} (path parameter)")
            elif p.location == 'body':
                param_list.append(f"{p.type} {p.name} (request body)")
            else:
                param_list.append(f"{p.type} {p.name} ({p.location} parameter)")
        
        return f"""Generate a Spring Boot delegate method body that implements this mapping:

EXTERNAL ENDPOINT (what the client calls):
- Path: {ext.path}
- Method: {ext.method}
- Operation ID: {ext.operation_id}
- Parameters: {', '.join(param_list) if param_list else 'none'}
- Response Type: {ext.response_type or 'void'}

INTERNAL API CALL (what we need to invoke):
- Base URL: {internal_base_url}
- Path: {internal.path}
- Method: {internal.method}
- Operation ID: {internal.operation_id}

PARAMETER MAPPING:
{json.dumps(mapping.param_mapping, indent=2)}

IMPLEMENTATION REQUIREMENTS:
1. Use WebClient (assume it's injected as 'webClient') to call the internal API
2. Build the full URL using base URL + path with path variables substituted
3. Map external parameters to internal API call according to the mapping
4. Handle 404 responses by returning ResponseEntity.notFound().build()
5. Handle other errors appropriately
6. Map the internal API response to the external response type
7. Add log.debug() statements for request/response
8. Return ResponseEntity with appropriate status code

Generate ONLY the method body code (the content inside the method {{ }}):
"""
    
    def _clean_generated_code(self, code: str) -> str:
        """Clean and extract Java code from LLM response"""
        # Remove markdown code blocks
        code = re.sub(r'```java\n?', '', code)
        code = re.sub(r'```\n?', '', code)
        
        # Remove method signatures if accidentally included
        lines = code.split('\n')
        filtered = []
        skip = False
        
        for line in lines:
            stripped = line.strip()
            
            # Skip method signatures
            if re.match(r'(public|private|protected|@Override).*\(.*\).*\{?$', stripped):
                skip = True
                if '{' in stripped:
                    skip = False
                continue
            
            if skip and '{' in stripped:
                skip = False
                continue
            
            if not skip:
                filtered.append(line)
        
        return '\n'.join(filtered).strip()
    
    def _generate_fallback(self, mapping: EndpointMapping) -> str:
        """Generate basic fallback implementation"""
        ext = mapping.external_endpoint
        internal = mapping.internal_endpoint
        
        return f"""log.debug("Handling {ext.method} request for {ext.path}");

// Build internal API URL
String url = internalBaseUrl + "{internal.path}";

// TODO: Map parameters and make WebClient call
throw new UnsupportedOperationException("Implementation pending for {ext.operation_id}");"""


# ============================================================================
# JAVA FILE INJECTOR
# ============================================================================

class JavaDelegateInjector:
    """Inject generated code into existing Java delegate classes"""
    
    def __init__(self, delegate_dir: str):
        self.delegate_dir = Path(delegate_dir)
    
    def inject_method(
        self,
        class_name: str,
        method_name: str,
        parameters: List[Parameter],
        return_type: str,
        method_body: str
    ) -> str:
        """Inject or update method in delegate class"""
        
        java_file = self.delegate_dir / f"{class_name}.java"
        
        if not java_file.exists():
            raise FileNotFoundError(f"Delegate class not found: {java_file}")
        
        with open(java_file, 'r') as f:
            content = f.read()
        
        # Build method signature
        signature = self._build_signature(method_name, parameters, return_type)
        
        # Check if method already exists
        method_pattern = rf'@Override\s+public\s+ResponseEntity<.*?>\s+{re.escape(method_name)}\s*\([^)]*\)'
        
        if re.search(method_pattern, content):
            # Update existing method
            content = self._update_existing_method(content, method_name, method_body)
        else:
            # Add new method
            content = self._add_new_method(content, signature, method_body)
        
        # Write updated content
        with open(java_file, 'w') as f:
            f.write(content)
        
        return str(java_file)
    
    def _build_signature(
        self,
        method_name: str,
        parameters: List[Parameter],
        return_type: str
    ) -> str:
        """Build Java method signature"""
        
        params = []
        for p in parameters:
            if p.location == 'path':
                params.append(f"@PathVariable String {p.name}")
            elif p.location == 'query':
                params.append(f"@RequestParam String {p.name}")
            elif p.location == 'body':
                params.append(f"@RequestBody {p.type} {p.name}")
        
        param_str = ', '.join(params) if params else ''
        response_type = return_type if return_type else '?'
        
        return f"@Override\n    public ResponseEntity<{response_type}> {method_name}({param_str})"
    
    def _update_existing_method(self, content: str, method_name: str, new_body: str) -> str:
        """Replace existing method body"""
        
        # Find method start
        pattern = rf'(@Override\s+public\s+ResponseEntity<.*?>\s+{re.escape(method_name)}\s*\([^)]*\)\s*\{{)'
        match = re.search(pattern, content, re.DOTALL)
        
        if not match:
            return content
        
        method_start = match.end()
        
        # Find matching closing brace
        brace_count = 1
        i = method_start
        while i < len(content) and brace_count > 0:
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
            i += 1
        
        method_end = i - 1
        
        # Replace body
        indented_body = self._indent_code(new_body, 2)
        new_content = (
            content[:method_start] +
            '\n' + indented_body + '\n    ' +
            content[method_end:]
        )
        
        return new_content
    
    def _add_new_method(self, content: str, signature: str, body: str) -> str:
        """Add new method before the last closing brace"""
        
        # Find last closing brace of class
        last_brace = content.rfind('}')
        
        if last_brace == -1:
            raise ValueError("Invalid Java class structure")
        
        indented_body = self._indent_code(body, 2)
        
        method = f"""
    {signature} {{
{indented_body}
    }}
"""
        
        new_content = content[:last_brace] + method + '\n' + content[last_brace:]
        
        return new_content
    
    def _indent_code(self, code: str, levels: int) -> str:
        """Indent code by specified levels (4 spaces each)"""
        indent = '    ' * levels
        lines = code.split('\n')
        return '\n'.join(indent + line if line.strip() else '' for line in lines)


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

class SpringBootAutomation:
    """Main automation orchestrator"""
    
    def __init__(
        self,
        external_oas: str,
        internal_oas: str,
        mapping_file: Optional[str],
        delegate_dir: str,
        output_dir: str,
        llm_model: str = "bedrock/amazon.nova-lite-v1:0"
    ):
        self.external_parser = OASParser(external_oas)
        self.internal_parser = OASParser(internal_oas)
        self.mapper = EndpointMapper(mapping_file)
        self.code_generator = DelegateCodeGenerator(llm_model)
        self.injector = JavaDelegateInjector(delegate_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def run(self):
        """Execute the full automation workflow"""
        
        print("=" * 80)
        print("SPRING BOOT DELEGATE AUTO-GENERATION")
        print("=" * 80)
        
        # Step 1: Parse OAS files
        print("\n📖 Step 1: Parsing OpenAPI Specifications...")
        external_endpoints = self.external_parser.parse_endpoints()
        internal_endpoints = self.internal_parser.parse_endpoints()
        internal_base_url = self.internal_parser.get_base_path()
        
        print(f"   ✓ Found {len(external_endpoints)} external endpoints")
        print(f"   ✓ Found {len(internal_endpoints)} internal endpoints")
        
        # Step 2: Map endpoints
        print("\n🔗 Step 2: Mapping external to internal endpoints...")
        mappings = self.mapper.map_endpoints(external_endpoints, internal_endpoints)
        print(f"   ✓ Created {len(mappings)} endpoint mappings")
        
        # Step 3: Generate and inject code
        print("\n🤖 Step 3: Generating and injecting method implementations...")
        
        generated_count = 0
        failed_count = 0
        
        for mapping in mappings:
            ext_ep = mapping.external_endpoint
            print(f"\n   Processing: {ext_ep.method} {ext_ep.path}")
            print(f"   → {ext_ep.operation_id}")
            
            try:
                # Generate method body
                print(f"     🔄 Generating code via LLM...")
                method_body = self.code_generator.generate_method_body(
                    mapping,
                    internal_base_url
                )
                
                # Determine delegate class name
                class_name = f"{ext_ep.tag.capitalize()}ApiDelegateImpl"
                
                # Inject into delegate
                print(f"     💉 Injecting into {class_name}...")
                file_path = self.injector.inject_method(
                    class_name=class_name,
                    method_name=ext_ep.operation_id,
                    parameters=ext_ep.parameters,
                    return_type=ext_ep.response_type or '?',
                    method_body=method_body
                )
                
                print(f"     ✅ Success! Updated {file_path}")
                generated_count += 1
                
            except Exception as e:
                print(f"     ❌ Failed: {e}")
                failed_count += 1
        
        # Summary
        print("\n" + "=" * 80)
        print("GENERATION COMPLETE")
        print("=" * 80)
        print(f"✅ Successfully generated: {generated_count}")
        print(f"❌ Failed: {failed_count}")
        print(f"📁 Delegate classes updated in: {self.injector.delegate_dir}")


# ============================================================================
# EXAMPLE / SETUP
# ============================================================================

def create_example_files():
    """Create example OAS and mapping files"""
    
    example_dir = Path("./example_project")
    example_dir.mkdir(exist_ok=True)
    
    # External OAS
    external_oas = {
        "openapi": "3.0.0",
        "info": {
            "title": "User Management API",
            "version": "1.0.0"
        },
        "servers": [
            {"url": "http://localhost:8080"}
        ],
        "paths": {
            "/api/users/{userId}": {
                "get": {
                    "tags": ["users"],
                    "operationId": "getUserById",
                    "summary": "Get user by ID",
                    "parameters": [
                        {
                            "name": "userId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "User found",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/User"
                                    }
                                }
                            }
                        },
                        "404": {
                            "description": "User not found"
                        }
                    }
                }
            },
            "/api/users": {
                "post": {
                    "tags": ["users"],
                    "operationId": "createUser",
                    "summary": "Create new user",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/CreateUserRequest"
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "User created",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/User"
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "User": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "email": {"type": "string"}
                    }
                },
                "CreateUserRequest": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "email": {"type": "string"}
                    }
                }
            }
        }
    }
    
    # Internal OAS
    internal_oas = {
        "openapi": "3.0.0",
        "info": {
            "title": "Internal User Service",
            "version": "1.0.0"
        },
        "servers": [
            {"url": "http://internal-service:9090"}
        ],
        "paths": {
            "/internal/v1/users/{id}": {
                "get": {
                    "operationId": "fetchUserById",
                    "summary": "Fetch user details",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Success",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/UserDetail"
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/internal/v1/users": {
                "post": {
                    "operationId": "registerUser",
                    "summary": "Register new user",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/UserRegistration"
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "Created",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/UserDetail"
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "UserDetail": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "fullName": {"type": "string"},
                        "emailAddress": {"type": "string"}
                    }
                },
                "UserRegistration": {
                    "type": "object",
                    "properties": {
                        "fullName": {"type": "string"},
                        "emailAddress": {"type": "string"}
                    }
                }
            }
        }
    }
    
    # Mapping file
    mapping = {
        "mappings": [
            {
                "external_operation_id": "getUserById",
                "internal_operation_id": "fetchUserById",
                "param_mapping": {
                    "userId": "id"
                }
            },
            {
                "external_operation_id": "createUser",
                "internal_operation_id": "registerUser",
                "param_mapping": {
                    "body": "body"
                }
            }
        ]
    }
    
    # Sample delegate class
    delegate_class = """package com.example.api.delegate;

import com.example.api.model.*;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

@Slf4j
@Component
@RequiredArgsConstructor
public class UsersApiDelegateImpl implements UsersApiDelegate {
    
    private final WebClient webClient;
    private final String internalBaseUrl = "http://internal-service:9090";
    
    // Generated methods will be injected here
    
}
"""
    
    # Write files
    with open(example_dir / "external.yaml", "w") as f:
        yaml.dump(external_oas, f, sort_keys=False)
    
    with open(example_dir / "internal.yaml", "w") as f:
        yaml.dump(internal_oas, f, sort_keys=False)
    
    with open(example_dir / "mapping.yaml", "w") as f:
        yaml.dump(mapping, f, sort_keys=False)
    
    # Create delegate directory
    delegate_dir = example_dir / "delegates"
    delegate_dir.mkdir(exist_ok=True)
    
    with open(delegate_dir / "UsersApiDelegateImpl.java", "w") as f:
        f.write(delegate_class)
    
    print("✅ Example files created in ./example_project/")
    print("\nFiles created:")
    print("  📄 external.yaml - External API specification")
    print("  📄 internal.yaml - Internal API specification")
    print("  📄 mapping.yaml - Endpoint mappings")
    print("  📄 delegates/UsersApiDelegateImpl.java - Sample delegate class")
    print("\nNext steps:")
    print("  1. Install dependencies: pip install litellm pyyaml boto3")
    print("  2. Configure AWS credentials for Bedrock")
    print("  3. Run: python generate_logic.py")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        create_example_files()
    elif len(sys.argv) > 1 and sys.argv[1] == "run":
        # Run the automation
        automation = SpringBootAutomation(
            external_oas="./example_project/external.yaml",
            internal_oas="./example_project/internal.yaml",
            mapping_file="./example_project/mapping.yaml",
            delegate_dir="./example_project/delegates",
            output_dir="./example_project/output"
        )
        automation.run()
    else:
        print("Spring Boot Delegate Auto-Generation")
        print("\nUsage:")
        print("  python generate_logic.py setup  - Create example files")
