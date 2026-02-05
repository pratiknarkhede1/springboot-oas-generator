# api_bridge_generator.py
import json
import yaml
import os
import shutil
from pathlib import Path
from typing import Dict, Any, List
import subprocess
import sys
import re


class APIBridgeGenerator:
    """
    Generates runnable Spring Boot code that bridges external and internal APIs.
    """
    
    def __init__(self, external_oas_path: str, internal_oas_path: str, output_dir: str):
        self.external_oas_path = external_oas_path
        self.internal_oas_path = internal_oas_path
        self.output_dir = output_dir
        self.template_dir = os.path.join(output_dir, "templates")
        self.generated_dir = os.path.join(output_dir, "generated")
        self.external_spec = self._load_spec(external_oas_path)
        self.internal_spec = self._load_spec(internal_oas_path)
        
    def _load_spec(self, path: str) -> Dict[str, Any]:
        """Load OAS file (JSON or YAML)"""
        with open(path, 'r') as f:
            if path.endswith('.json'):
                return json.load(f)
            else:
                return yaml.safe_load(f)
    
    def _get_java_type(self, schema_type: str, schema_format: str = None) -> str:
        """Convert OpenAPI type to Java type"""
        type_mapping = {
            'string': 'String',
            'integer': 'Integer' if schema_format != 'int64' else 'Long',
            'number': 'Double' if schema_format == 'double' else 'Float',
            'boolean': 'Boolean',
            'array': 'List',
            'object': 'Object'
        }
        return type_mapping.get(schema_type, 'Object')
    
    def _extract_operations(self, spec: Dict[str, Any]) -> List[Dict]:
        """Extract all operations from OpenAPI spec"""
        operations = []
        paths = spec.get('paths', {})
        
        for path, path_item in paths.items():
            for method in ['get', 'post', 'put', 'delete', 'patch']:
                if method in path_item:
                    operation = path_item[method]
                    operations.append({
                        'path': path,
                        'method': method,
                        'operationId': operation.get('operationId', f"{method}_{path.replace('/', '_').replace('{', '').replace('}', '')}"),
                        'summary': operation.get('summary', ''),
                        'parameters': operation.get('parameters', []),
                        'requestBody': operation.get('requestBody', {}),
                        'responses': operation.get('responses', {})
                    })
        
        return operations
    
    def _create_templates(self):
        """Create all necessary Mustache templates"""
        os.makedirs(self.template_dir, exist_ok=True)
        
        # API Controller template
        api_template = """package {{package}};

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
{{#reactive}}
import reactor.core.publisher.Mono;
{{/reactive}}
{{#imports}}
import {{import}};
{{/imports}}

{{#operations}}
@RestController
public class {{classname}} {

    private final {{classname}}Service service;
    
    @Autowired
    public {{classname}}({{classname}}Service service) {
        this.service = service;
    }
{{#operation}}

    @{{httpMethod}}("{{path}}")
    public {{#reactive}}Mono<{{/reactive}}ResponseEntity<{{#returnType}}{{{returnType}}}{{/returnType}}{{^returnType}}Void{{/returnType}}>{{#reactive}}>{{/reactive}} {{operationId}}(
            {{#allParams}}@{{#isPathParam}}PathVariable{{/isPathParam}}{{#isQueryParam}}RequestParam{{/isQueryParam}}{{#isHeaderParam}}RequestHeader{{/isHeaderParam}}{{#isBodyParam}}RequestBody{{/isBodyParam}}{{#hasMore}} {{/hasMore}}{{{dataType}}} {{paramName}}{{^-last}},
            {{/-last}}{{/allParams}}{{^hasParams}}{{/hasParams}}) {
        {{#returnType}}return {{/returnType}}{{^returnType}}{{/returnType}}service.{{operationId}}({{#allParams}}{{paramName}}{{^-last}}, {{/-last}}{{/allParams}});
        {{^returnType}}return {{#reactive}}Mono.just({{/reactive}}ResponseEntity.ok().build(){{#reactive}}){{/reactive}};{{/returnType}}
    }
{{/operation}}
}
{{/operations}}
"""
        
        with open(os.path.join(self.template_dir, "api.mustache"), 'w') as f:
            f.write(api_template)
        
        # POM template
        pom_template = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 
         http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>{{groupId}}</groupId>
    <artifactId>{{artifactId}}</artifactId>
    <version>{{artifactVersion}}</version>
    <packaging>jar</packaging>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.0</version>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>io.swagger.core.v3</groupId>
            <artifactId>swagger-annotations</artifactId>
            <version>2.2.20</version>
        </dependency>
        <dependency>
            <groupId>org.openapitools</groupId>
            <artifactId>jackson-databind-nullable</artifactId>
            <version>0.2.6</version>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.datatype</groupId>
            <artifactId>jackson-datatype-jsr310</artifactId>
        </dependency>
        <dependency>
            <groupId>jakarta.validation</groupId>
            <artifactId>jakarta.validation-api</artifactId>
        </dependency>
        <dependency>
            <groupId>jakarta.annotation</groupId>
            <artifactId>jakarta.annotation-api</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
"""
        
        with open(os.path.join(self.template_dir, "pom.mustache"), 'w') as f:
            f.write(pom_template)
    
    def generate(self):
        """Main generation workflow"""
        print("=" * 70)
        print("API BRIDGE GENERATOR - Spring Boot Code Generation")
        print("=" * 70)
        
        # Step 1: Create templates
        print("\n[1/5] Creating Mustache templates...")
        self._create_templates()
        
        # Step 2: Generate base code with OpenAPI Generator
        print("[2/5] Running OpenAPI Generator...")
        self._run_generator()
        
        # Step 3: Generate service classes
        print("[3/5] Generating service classes...")
        self._generate_service_classes()
        
        # Step 4: Generate configuration classes
        print("[4/5] Generating configuration classes...")
        self._generate_config_classes()
        
        # Step 5: Fix compilation errors
        print("[5/5] Fixing generated code...")
        self._fix_generated_code()
        
        print("\n" + "=" * 70)
        print("✓ GENERATION COMPLETE!")
        print("=" * 70)
        print(f"\nLocation: {self.generated_dir}")
        print("\nTo run:")
        print(f"  cd {self.generated_dir}")
        print("  ./mvnw clean spring-boot:run")
        
        return self.generated_dir
    
    def _run_generator(self):
        """Run OpenAPI Generator"""
        config = {
            "generatorName": "spring",
            "library": "spring-boot",
            "apiPackage": "com.generated.api",
            "modelPackage": "com.generated.model",
            "invokerPackage": "com.generated",
            "groupId": "com.generated",
            "artifactId": "api-bridge",
            "artifactVersion": "1.0.0",
            "additionalProperties": {
                "java8": "false",
                "useSpringBoot3": "true",
                "interfaceOnly": "false",
                "skipDefaultInterface": "true",
                "useTags": "false",
                "delegatePattern": "false"
            }
        }
        
        config_path = os.path.join(self.output_dir, "config.json")
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        try:
            cmd = [
                "docker", "run", "--rm",
                "-v", f"{os.path.abspath(self.external_oas_path)}:/spec/api.yaml",
                "-v", f"{os.path.abspath(self.generated_dir)}:/out",
                "-v", f"{os.path.abspath(config_path)}:/config.json",
                "openapitools/openapi-generator-cli", "generate",
                "-i", "/spec/api.yaml",
                "-g", "spring",
                "-o", "/out",
                "-c", "/config.json",
                "--additional-properties=useSpringBoot3=true,interfaceOnly=false,skipDefaultInterface=true"
            ]
            
            subprocess.run(cmd, check=True, capture_output=True)
            print("  ✓ Base code generated")
        except subprocess.CalledProcessError as e:
            print(f"  Error: {e.stderr.decode()}")
            raise
    
    def _generate_service_classes(self):
        """Generate service classes for each API"""
        operations = self._extract_operations(self.external_spec)
        internal_operations = self._extract_operations(self.internal_spec)
        
        # Group operations by tag or path
        api_groups = {}
        for op in operations:
            # Use first path segment as group name
            parts = op['path'].strip('/').split('/')
            group = parts[0].capitalize() if parts else 'Default'
            
            if group not in api_groups:
                api_groups[group] = []
            api_groups[group].append(op)
        
        # Generate a service class for each group
        for group_name, group_ops in api_groups.items():
            self._create_service_file(group_name, group_ops, internal_operations)
    
    def _create_service_file(self, class_name: str, operations: List[Dict], internal_ops: List[Dict]):
        """Create a service class file"""
        service_dir = os.path.join(self.generated_dir, "src/main/java/com/generated/service")
        os.makedirs(service_dir, exist_ok=True)
        
        internal_base_url = "http://localhost:8081"
        if self.internal_spec.get('servers'):
            internal_base_url = self.internal_spec['servers'][0].get('url', internal_base_url)
        
        service_code = f"""package com.generated.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import com.generated.model.*;

@Service
public class {class_name}ApiService {{

    private final WebClient webClient;
    
    @Value("${{internal.api.base-url:{internal_base_url}}}")
    private String internalApiBaseUrl;
    
    public {class_name}ApiService(WebClient.Builder webClientBuilder) {{
        this.webClient = webClientBuilder.build();
    }}
"""
        
        for op in operations:
            # Extract parameters
            params = []
            param_names = []
            
            for param in op['parameters']:
                param_type = self._get_java_type(
                    param.get('schema', {}).get('type', 'string'),
                    param.get('schema', {}).get('format')
                )
                param_name = param['name']
                params.append(f"{param_type} {param_name}")
                param_names.append(param_name)
            
            # Check for request body
            if op['requestBody']:
                params.append("Object requestBody")
                param_names.append("requestBody")
            
            params_str = ", ".join(params) if params else ""
            
            # Determine return type
            return_type = "Object"
            if '200' in op['responses']:
                response_schema = op['responses']['200'].get('content', {}).get('application/json', {}).get('schema', {})
                if response_schema:
                    return_type = response_schema.get('$ref', 'Object').split('/')[-1] if '$ref' in response_schema else 'Object'
            
            # Find matching internal operation
            internal_path = self._find_matching_internal_path(op, internal_ops)
            
            method_code = f"""
    public Mono<ResponseEntity<{return_type}>> {op['operationId']}({params_str}) {{
        return webClient
            .method(org.springframework.http.HttpMethod.{op['method'].upper()})
            .uri(internalApiBaseUrl + "{internal_path}")
"""
            
            # Add body if present
            if op['requestBody']:
                method_code += """            .bodyValue(requestBody)
"""
            
            method_code += f"""            .retrieve()
            .toEntity({return_type}.class);
    }}
"""
            
            service_code += method_code
        
        service_code += "}\n"
        
        # Write service file
        service_file = os.path.join(service_dir, f"{class_name}ApiService.java")
        with open(service_file, 'w') as f:
            f.write(service_code)
        
        print(f"  ✓ Generated {class_name}ApiService.java")
    
    def _find_matching_internal_path(self, external_op: Dict, internal_ops: List[Dict]) -> str:
        """Find matching internal API path"""
        # Simple matching by operation ID or path similarity
        for internal_op in internal_ops:
            if internal_op['operationId'] == external_op['operationId']:
                return internal_op['path']
            if internal_op['path'].split('/')[-1] == external_op['path'].split('/')[-1]:
                return internal_op['path']
        
        # Default to same path
        return external_op['path']
    
    def _generate_config_classes(self):
        """Generate Spring configuration classes"""
        config_dir = os.path.join(self.generated_dir, "src/main/java/com/generated/config")
        os.makedirs(config_dir, exist_ok=True)
        
        # WebClient configuration
        webclient_config = """package com.generated.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfig {
    
    @Bean
    public WebClient.Builder webClientBuilder() {
        return WebClient.builder();
    }
}
"""
        
        with open(os.path.join(config_dir, "WebClientConfig.java"), 'w') as f:
            f.write(webclient_config)
        
        # Application main class
        app_dir = os.path.join(self.generated_dir, "src/main/java/com/generated")
        app_class = """package com.generated;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
"""
        
        with open(os.path.join(app_dir, "Application.java"), 'w') as f:
            f.write(app_class)
        
        # application.properties
        resources_dir = os.path.join(self.generated_dir, "src/main/resources")
        os.makedirs(resources_dir, exist_ok=True)
        
        internal_base_url = "http://localhost:8081"
        if self.internal_spec.get('servers'):
            internal_base_url = self.internal_spec['servers'][0].get('url', internal_base_url)
        
        app_properties = f"""server.port=8080
internal.api.base-url={internal_base_url}
logging.level.com.generated=DEBUG
"""
        
        with open(os.path.join(resources_dir, "application.properties"), 'w') as f:
            f.write(app_properties)
        
        print("  ✓ Generated configuration classes")
    
    def _fix_generated_code(self):
        """Fix common issues in generated code"""
        api_dir = os.path.join(self.generated_dir, "src/main/java/com/generated/api")
        
        if not os.path.exists(api_dir):
            print("  ! Warning: API directory not found")
            return
        
        # Find and update API controller files
        for root, dirs, files in os.walk(api_dir):
            for file in files:
                if file.endswith("Api.java") and not file.endswith("Controller.java"):
                    file_path = os.path.join(root, file)
                    self._update_controller_file(file_path)
        
        print("  ✓ Fixed controller files")
    
    def _update_controller_file(self, file_path: str):
        """Update controller file to inject and use service"""
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Extract class name
        class_match = re.search(r'public class (\w+)', content)
        if not class_match:
            return
        
        class_name = class_match.group(1).replace('Api', '')
        
        # Add service injection
        if '@Autowired' not in content:
            # Add import
            if 'import org.springframework.beans.factory.annotation.Autowired;' not in content:
                content = content.replace(
                    'package com.generated.api;',
                    'package com.generated.api;\n\nimport org.springframework.beans.factory.annotation.Autowired;'
                )
            
            # Add service import
            content = content.replace(
                'package com.generated.api;',
                f'package com.generated.api;\n\nimport com.generated.service.{class_name}ApiService;'
            )
            
            # Add service field and constructor
            service_injection = f"""
    private final {class_name}ApiService service;
    
    @Autowired
    public {class_match.group(1)}({class_name}ApiService service) {{
        this.service = service;
    }}
"""
            
            # Insert after class declaration
            content = re.sub(
                r'(public class \w+ \{)',
                r'\1' + service_injection,
                content
            )
        
        # Update method bodies to call service
        # This is a simplified approach - you may need to customize based on your needs
        content = re.sub(
            r'return new ResponseEntity<>\(HttpStatus\.NOT_IMPLEMENTED\);',
            lambda m: 'return service.' + self._extract_method_name(content, m.start()) + '();',
            content
        )
        
        with open(file_path, 'w') as f:
            f.write(content)
    
    def _extract_method_name(self, content: str, position: int) -> str:
        """Extract method name from content at position"""
        # Look backwards to find method name
        before = content[:position]
        method_match = re.findall(r'public \w+<?\w*>? (\w+)\(', before)
        if method_match:
            return method_match[-1]
        return "unknownMethod"


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate Spring Boot API Bridge')
    parser.add_argument('--external', required=True, help='External OAS file')
    parser.add_argument('--internal', required=True, help='Internal OAS file')
    parser.add_argument('--output', default='./output', help='Output directory')
    
    args = parser.parse_args()
    
    generator = APIBridgeGenerator(
        external_oas_path=args.external,
        internal_oas_path=args.internal,
        output_dir=args.output
    )
    
    try:
        generator.generate()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
