#!/usr/bin/env python3
"""
Spring Boot Service Generator
Generates Spring Boot services from OpenAPI specs with LLM-powered service layer
"""

import os
import sys
import yaml
import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class OpenAPIGenerator:
    """Wrapper for OpenAPI Generator CLI"""
    
    def __init__(self):
        self._verify_installation()
    
    def _verify_installation(self):
        """Check if openapi-generator-cli is installed"""
        try:
            subprocess.run(
                ["openapi-generator-cli", "version"],
                check=True,
                capture_output=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("openapi-generator-cli not found. Install it via npm or brew")
            sys.exit(1)
    
    def generate_server(self, spec_path: str, output_dir: str, package_name: str) -> str:
        """Generate Spring Boot server stubs"""
        
        logger.info(f"Generating server stubs from {spec_path}")
        
        os.makedirs(output_dir, exist_ok=True)
        
        config = {
            "basePackage": package_name,
            "apiPackage": f"{package_name}.api",
            "modelPackage": f"{package_name}.model",
            "configPackage": f"{package_name}.config",
            "interfaceOnly": "false",
            "delegatePattern": "true",
            "useTags": "true",
            "dateLibrary": "java8",
            "useSpringBoot3": "true",
            "java17": "true",
            "skipDefaultInterface": "true"
        }
        
        config_file = f"{output_dir}/server-config.json"
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        cmd = [
            "openapi-generator-cli", "generate",
            "-i", spec_path,
            "-g", "spring",
            "-o", output_dir,
            "-c", config_file,
            "--additional-properties",
            "groupId=com.generated,artifactId=generated-service,artifactVersion=1.0.0"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )
            logger.info("Server generation successful")
            logger.debug(result.stdout)
            return output_dir
        except subprocess.CalledProcessError as e:
            logger.error(f"Server generation failed: {e.stderr}")
            raise
    
    def generate_client(self, spec_path: str, output_dir: str, 
                       package_name: str, client_name: str) -> str:
        """Generate Java REST client"""
        
        logger.info(f"Generating client {client_name} from {spec_path}")
        
        os.makedirs(output_dir, exist_ok=True)
        
        config = {
            "basePackage": package_name,
            "apiPackage": f"{package_name}.api",
            "modelPackage": f"{package_name}.model",
            "invokerPackage": f"{package_name}.invoker",
            "library": "resttemplate",
            "dateLibrary": "java8",
            "java17": "true"
        }
        
        config_file = f"{output_dir}/client-config.json"
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        cmd = [
            "openapi-generator-cli", "generate",
            "-i", spec_path,
            "-g", "java",
            "-o", output_dir,
            "-c", config_file
        ]
        
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )
            logger.info(f"Client {client_name} generation successful")
            return output_dir
        except subprocess.CalledProcessError as e:
            logger.error(f"Client generation failed: {e.stderr}")
            raise


class LLMService:
    """Service for LLM-based code generation"""
    
    def __init__(self, bedrock_region: str, model_id: str):
        self.bedrock_region = bedrock_region
        self.model_id = model_id
        self._verify_dependencies()
    
    def _verify_dependencies(self):
        """Check if litellm and boto3 are installed"""
        try:
            import litellm
            import boto3
        except ImportError as e:
            logger.error(f"Missing dependency: {e}")
            logger.error("Install with: pip install litellm boto3")
            sys.exit(1)
    
    def generate_service_layer(self, context: Dict[str, Any]) -> Dict[str, str]:
        """Generate service layer code using LLM"""
        
        logger.info("Generating service layer with LLM...")
        
        from litellm import completion
        
        prompt = self._build_prompt(context)
        
        try:
            response = completion(
                model=f"bedrock/{self.model_id}",
                messages=[
                    {
                        "role": "system",
                        "content": self._get_system_prompt()
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                aws_region_name=self.bedrock_region,
                temperature=0.2,
                max_tokens=4000
            )
            
            code_files = self._parse_response(response.choices[0].message.content)
            logger.info(f"Generated {len(code_files)} service files")
            
            return code_files
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            # Return fallback template
            return self._get_fallback_service(context)
    
    def _get_system_prompt(self) -> str:
        return """You are an expert Spring Boot developer. Generate production-ready service implementation code.

Requirements:
- Use Spring Boot 3 with Java 17
- Implement proper error handling
- Add appropriate logging with SLF4J
- Use constructor injection
- Follow Spring best practices
- Include proper JavaDoc comments
- Handle null safety

Output ONLY valid Java code wrapped in ```java blocks."""
    
    def _build_prompt(self, context: Dict[str, Any]) -> str:
        """Build detailed prompt for LLM"""
        
        external = context['external_api']
        internals = context['internal_apis']
        package = context['package_name']
        
        prompt = f"""Generate Spring Boot service implementation for this API mapping:

PACKAGE: {package}

EXTERNAL API ENDPOINTS (to implement):
{json.dumps(external['endpoints'], indent=2)}

INTERNAL API CLIENTS (available to call):
{json.dumps([{
    'name': api['name'],
    'endpoints': api['endpoints']
} for api in internals], indent=2)}

Generate ONE service class that:
1. Implements the API delegate interface
2. Calls internal API clients as needed
3. Maps between external and internal models
4. Handles errors with proper HTTP status codes

Class name: ExternalApiDelegateImpl
Package: {package}.service

Return ONLY the Java code in ```java``` blocks."""
        
        return prompt
    
    def _parse_response(self, response_text: str) -> Dict[str, str]:
        """Extract Java code from LLM response"""
        
        code_files = {}
        
        # Extract code blocks
        import re
        code_blocks = re.findall(r'```java\n(.*?)```', response_text, re.DOTALL)
        
        for i, code in enumerate(code_blocks):
            # Try to extract class name
            class_match = re.search(r'public\s+class\s+(\w+)', code)
            if class_match:
                filename = f"{class_match.group(1)}.java"
            else:
                filename = f"GeneratedService{i}.java"
            
            code_files[filename] = code.strip()
        
        if not code_files:
            raise ValueError("No valid Java code found in LLM response")
        
        return code_files
    
    def _get_fallback_service(self, context: Dict[str, Any]) -> Dict[str, str]:
        """Return a simple fallback service template"""
        
        package = context['package_name']
        
        code = f"""package {package}.service;

import {package}.api.*;
import org.springframework.stereotype.Service;
import org.springframework.http.ResponseEntity;
import lombok.extern.slf4j.Slf4j;

@Slf4j
@Service
public class FallbackDelegateImpl implements ApiDelegate {{
    
    // TODO: Implement API methods
    
}}
"""
        
        return {"FallbackDelegateImpl.java": code}


class ProjectMerger:
    """Merges generated code into a single Spring Boot project"""
    
    def __init__(self, package_name: str):
        self.package_name = package_name
    
    def merge(self, server_dir: str, client_dirs: List[str], 
              service_code: Dict[str, str], output_dir: str) -> str:
        """Merge all components into final project"""
        
        logger.info("Merging generated code...")
        
        final_dir = output_dir
        os.makedirs(final_dir, exist_ok=True)
        
        # Copy server base
        self._copy_directory(f"{server_dir}/src", f"{final_dir}/src")
        
        # Copy client libraries
        for client_dir in client_dirs:
            client_src = f"{client_dir}/src/main/java"
            if os.path.exists(client_src):
                self._copy_directory(client_src, f"{final_dir}/src/main/java")
        
        # Write service layer
        service_dir = f"{final_dir}/src/main/java/{self.package_name.replace('.', '/')}/service"
        os.makedirs(service_dir, exist_ok=True)
        
        for filename, code in service_code.items():
            filepath = f"{service_dir}/{filename}"
            with open(filepath, 'w') as f:
                f.write(code)
            logger.info(f"Created {filepath}")
        
        # Generate pom.xml
        self._generate_pom(final_dir)
        
        # Generate application.properties
        self._generate_properties(final_dir)
        
        # Generate main application class
        self._generate_main_class(final_dir)
        
        return final_dir
    
    def _copy_directory(self, src: str, dst: str):
        """Copy directory with error handling"""
        if os.path.exists(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
    
    def _generate_pom(self, project_dir: str):
        """Generate pom.xml with all dependencies"""
        
        pom_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 
         http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.1</version>
    </parent>
    
    <groupId>com.generated</groupId>
    <artifactId>generated-service</artifactId>
    <version>1.0.0</version>
    
    <properties>
        <java.version>17</java.version>
        <maven.compiler.source>17</maven.compiler.source>
        <maven.compiler.target>17</maven.compiler.target>
    </properties>
    
    <dependencies>
        <!-- Spring Boot -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        
        <!-- OpenAPI -->
        <dependency>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
            <version>2.3.0</version>
        </dependency>
        
        <dependency>
            <groupId>io.swagger.core.v3</groupId>
            <artifactId>swagger-annotations</artifactId>
            <version>2.2.20</version>
        </dependency>
        
        <!-- Jackson -->
        <dependency>
            <groupId>com.fasterxml.jackson.datatype</groupId>
            <artifactId>jackson-datatype-jsr310</artifactId>
        </dependency>
        
        <!-- REST Client -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        
        <!-- Google Findbugs -->
        <dependency>
            <groupId>com.google.code.findbugs</groupId>
            <artifactId>jsr305</artifactId>
            <version>3.0.2</version>
        </dependency>
        
        <!-- Lombok -->
        <dependency>
            <groupId>org.projectlombok</groupId>
            <artifactId>lombok</artifactId>
            <optional>true</optional>
        </dependency>
        
        <!-- Testing -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
        
        with open(f"{project_dir}/pom.xml", 'w') as f:
            f.write(pom_content)
        
        logger.info("Generated pom.xml")
    
    def _generate_properties(self, project_dir: str):
        """Generate application.properties"""
        
        props_dir = f"{project_dir}/src/main/resources"
        os.makedirs(props_dir, exist_ok=True)
        
        properties = """server.port=8080
spring.application.name=generated-service

# Logging
logging.level.root=INFO
logging.level.{package}=DEBUG

# Jackson
spring.jackson.serialization.write-dates-as-timestamps=false
""".format(package=self.package_name)
        
        with open(f"{props_dir}/application.properties", 'w') as f:
            f.write(properties)
    
    def _generate_main_class(self, project_dir: str):
        """Generate Spring Boot main application class"""
        
        main_dir = f"{project_dir}/src/main/java/{self.package_name.replace('.', '/')}"
        os.makedirs(main_dir, exist_ok=True)
        
        main_class = f"""package {self.package_name};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GeneratedServiceApplication {{
    
    public static void main(String[] args) {{
        SpringApplication.run(GeneratedServiceApplication.class, args);
    }}
}}
"""
        
        with open(f"{main_dir}/GeneratedServiceApplication.java", 'w') as f:
            f.write(main_class)


class SpecAnalyzer:
    """Analyzes OpenAPI specs to build context"""
    
    @staticmethod
    def extract_endpoints(spec: Dict[str, Any]) -> List[Dict]:
        """Extract endpoint information"""
        endpoints = []
        
        for path, methods in spec.get('paths', {}).items():
            for method, details in methods.items():
                if method.lower() in ['get', 'post', 'put', 'delete', 'patch']:
                    endpoints.append({
                        'path': path,
                        'method': method.upper(),
                        'operationId': details.get('operationId', ''),
                        'summary': details.get('summary', ''),
                        'parameters': [p.get('name') for p in details.get('parameters', [])],
                        'hasRequestBody': 'requestBody' in details,
                        'responses': list(details.get('responses', {}).keys())
                    })
        
        return endpoints
    
    @staticmethod
    def extract_models(spec: Dict[str, Any]) -> Dict[str, Any]:
        """Extract model schemas"""
        return spec.get('components', {}).get('schemas', {})


class ServiceGenerator:
    """Main orchestrator for service generation"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.openapi_gen = OpenAPIGenerator()
        self.llm_service = LLMService(
            bedrock_region=config['bedrock']['region'],
            model_id=config['bedrock']['model_id']
        )
        self.analyzer = SpecAnalyzer()
        self.package_name = config['package_name']
        self.merger = ProjectMerger(self.package_name)
    
    def generate(self, external_api: str, internal_apis: List[str], output_dir: str) -> str:
        """Main generation pipeline"""
        
        logger.info("=" * 60)
        logger.info("Starting Service Generation")
        logger.info("=" * 60)
        
        temp_dir = f"{output_dir}/temp"
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            # Step 1: Generate server
            server_dir = self.openapi_gen.generate_server(
                spec_path=external_api,
                output_dir=f"{temp_dir}/server",
                package_name=self.package_name
            )
            
            # Step 2: Generate clients
            client_dirs = []
            for i, internal_api in enumerate(internal_apis):
                client_name = f"client{i}"
                client_pkg = f"{self.package_name}.clients.{client_name}"
                
                client_dir = self.openapi_gen.generate_client(
                    spec_path=internal_api,
                    output_dir=f"{temp_dir}/clients/{client_name}",
                    package_name=client_pkg,
                    client_name=client_name
                )
                client_dirs.append(client_dir)
            
            # Step 3: Analyze specs
            context = self._build_context(external_api, internal_apis)
            
            # Step 4: Generate service layer
            service_code = self.llm_service.generate_service_layer(context)
            
            # Step 5: Merge everything
            final_dir = f"{output_dir}/generated-service"
            self.merger.merge(server_dir, client_dirs, service_code, final_dir)
            
            # Step 6: Validate
            self._validate_project(final_dir)
            
            logger.info("=" * 60)
            logger.info(f"✅ Service generated successfully: {final_dir}")
            logger.info("=" * 60)
            logger.info(f"To build: cd {final_dir} && mvn clean install")
            logger.info(f"To run: cd {final_dir} && mvn spring-boot:run")
            
            return final_dir
            
        except Exception as e:
            logger.error(f"Generation failed: {e}", exc_info=True)
            raise
    
    def _build_context(self, external_api: str, internal_apis: List[str]) -> Dict[str, Any]:
        """Build context for LLM"""
        
        with open(external_api, 'r') as f:
            external_spec = yaml.safe_load(f)
        
        internal_specs = []
        for api_path in internal_apis:
            with open(api_path, 'r') as f:
                spec = yaml.safe_load(f)
                internal_specs.append({
                    'name': Path(api_path).stem,
                    'spec': spec
                })
        
        return {
            'package_name': self.package_name,
            'external_api': {
                'endpoints': self.analyzer.extract_endpoints(external_spec),
                'models': self.analyzer.extract_models(external_spec)
            },
            'internal_apis': [
                {
                    'name': api['name'],
                    'endpoints': self.analyzer.extract_endpoints(api['spec']),
                    'models': self.analyzer.extract_models(api['spec'])
                }
                for api in internal_specs
            ]
        }
    
    def _validate_project(self, project_dir: str):
        """Validate the generated project"""
        
        logger.info("Validating generated project...")
        
        # Check required files exist
        required_files = [
            "pom.xml",
            "src/main/java",
            "src/main/resources/application.properties"
        ]
        
        for req_file in required_files:
            path = f"{project_dir}/{req_file}"
            if not os.path.exists(path):
                logger.warning(f"Missing: {path}")
        
        # Try to compile (optional - requires Maven)
        if shutil.which("mvn"):
            logger.info("Attempting Maven compile...")
            try:
                result = subprocess.run(
                    ["mvn", "clean", "compile"],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if result.returncode == 0:
                    logger.info("✅ Maven compile successful!")
                else:
                    logger.warning("⚠️ Maven compile had issues:")
                    logger.warning(result.stderr)
            except subprocess.TimeoutExpired:
                logger.warning("Maven compile timeout")
            except Exception as e:
                logger.warning(f"Could not run Maven: {e}")
        else:
            logger.info("Maven not found - skipping compile check")


def main():
    """Main entry point"""
    
    # Example configuration
    config = {
        'package_name': 'com.example.generated',
        'bedrock': {
            'region': 'us-east-1',
            'model_id': 'anthropic.claude-3-5-sonnet-20241022-v2:0'
        }
    }
    
    generator = ServiceGenerator(config)
    
    # Example usage
    generator.generate(
        external_api='input/external-api.yaml',
        internal_apis=[
            'input/internal-apis/users-api.yaml',
            'input/internal-apis/orders-api.yaml'
        ],
        output_dir='output'
    )


if __name__ == "__main__":
    main()
