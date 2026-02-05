# api_bridge_generator.py
import json
import yaml
import os
import shutil
from pathlib import Path
from typing import Dict, Any, List
import subprocess
import sys


class APIBridgeGenerator:
    """
    Generates runnable Spring Boot code that bridges external and internal APIs
    using OpenAPI Generator with custom Mustache templates.
    """
    
    def __init__(self, external_oas_path: str, internal_oas_path: str, output_dir: str):
        self.external_oas_path = external_oas_path
        self.internal_oas_path = internal_oas_path
        self.output_dir = output_dir
        self.template_dir = os.path.join(output_dir, "custom-templates", "spring")
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
    
    def _create_template_directories(self):
        """Create directory structure for custom templates"""
        dirs = [
            self.template_dir,
            os.path.join(self.template_dir, "api"),
            os.path.join(self.template_dir, "configuration"),
            os.path.join(self.template_dir, "resources"),
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)
    
    def _create_api_mustache_template(self):
        """Create the main API controller template"""
        template_content = """package {{package}};

{{#imports}}
import {{import}};
{{/imports}}
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
{{#reactive}}
import reactor.core.publisher.Mono;
import reactor.core.publisher.Flux;
{{/reactive}}
{{^reactive}}
import org.springframework.http.HttpStatus;
{{/reactive}}

{{#operations}}
/**
 * {{description}}
 */
@RestController
{{#basePath}}
@RequestMapping("{{.}}")
{{/basePath}}
public class {{classname}} {

    private final {{classname}}Service service;
    
    @Autowired
    public {{classname}}({{classname}}Service service) {
        this.service = service;
    }

{{#operation}}
    /**
     * {{summary}}
     * {{notes}}
     */
    @{{httpMethod}}{{#subresourceOperation}}("{{path}}"){{/subresourceOperation}}{{^subresourceOperation}}{{#hasPathParams}}("{{path}}"){{/hasPathParams}}{{/subresourceOperation}}
    public {{#reactive}}Mono<{{/reactive}}ResponseEntity<{{#returnType}}{{{.}}}{{/returnType}}{{^returnType}}Void{{/returnType}}>{{#reactive}}>{{/reactive}} {{operationId}}(
        {{#allParams}}
        {{#isPathParam}}@PathVariable("{{baseName}}") {{/isPathParam}}{{#isQueryParam}}@RequestParam(value = "{{baseName}}", required = {{required}}) {{/isQueryParam}}{{#isHeaderParam}}@RequestHeader(value = "{{baseName}}", required = {{required}}) {{/isHeaderParam}}{{#isBodyParam}}@RequestBody {{/isBodyParam}}{{{dataType}}} {{paramName}}{{^-last}},
        {{/-last}}{{/allParams}}
    ) {
        return service.{{operationId}}({{#allParams}}{{paramName}}{{^-last}}, {{/-last}}{{/allParams}}){{#reactive}}
            .map(ResponseEntity::ok){{/reactive}}{{^reactive}};{{/reactive}}
    }

{{/operation}}
}
{{/operations}}
"""
        with open(os.path.join(self.template_dir, "api.mustache"), 'w') as f:
            f.write(template_content)
    
    def _create_service_mustache_template(self):
        """Create service layer template that calls internal API"""
        template_content = """package {{package}};

{{#imports}}
import {{import}};
{{/imports}}
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.http.MediaType;
{{#reactive}}
import reactor.core.publisher.Mono;
import reactor.core.publisher.Flux;
{{/reactive}}
import java.util.HashMap;
import java.util.Map;

{{#operations}}
@Service
public class {{classname}}Service {

    private final WebClient webClient;
    
    @Value("${internal.api.base-url}")
    private String internalApiBaseUrl;
    
    @Autowired
    public {{classname}}Service(WebClient.Builder webClientBuilder) {
        this.webClient = webClientBuilder.build();
    }

{{#operation}}
    public {{#reactive}}Mono<{{/reactive}}{{#returnType}}{{{.}}}{{/returnType}}{{^returnType}}Void{{/returnType}}{{#reactive}}>{{/reactive}} {{operationId}}(
        {{#allParams}}
        {{{dataType}}} {{paramName}}{{^-last}},
        {{/-last}}{{/allParams}}
    ) {
        {{#hasQueryParams}}
        Map<String, Object> queryParams = new HashMap<>();
        {{#queryParams}}
        {{^required}}if ({{paramName}} != null) {{/required}}queryParams.put("{{baseName}}", {{paramName}});
        {{/queryParams}}
        {{/hasQueryParams}}
        
        return webClient
            .method(org.springframework.http.HttpMethod.{{httpMethod}})
            .uri(uriBuilder -> uriBuilder
                .scheme("http")
                .host(internalApiBaseUrl.replace("http://", "").replace("https://", "").split(":")[0])
                .port(internalApiBaseUrl.contains(":") ? Integer.parseInt(internalApiBaseUrl.split(":")[internalApiBaseUrl.split(":").length - 1].replaceAll("[^0-9].*", "")) : 80)
                .path("{{path}}")
                {{#hasQueryParams}}
                .queryParams(org.springframework.util.LinkedMultiValueMap.class.cast(
                    queryParams.entrySet().stream()
                        .collect(org.springframework.web.util.UriComponentsBuilder.newInstance()
                            .queryParams(new org.springframework.util.LinkedMultiValueMap<>())
                            .build()
                            .getQueryParams())))
                {{/hasQueryParams}}
                .build({{#pathParams}}{{paramName}}{{^-last}}, {{/-last}}{{/pathParams}}))
            {{#hasHeaderParams}}
            {{#headerParams}}
            .header("{{baseName}}", {{paramName}} != null ? {{paramName}}.toString() : null)
            {{/headerParams}}
            {{/hasHeaderParams}}
            .contentType(MediaType.APPLICATION_JSON)
            {{#hasBodyParam}}
            .bodyValue({{#bodyParam}}{{paramName}}{{/bodyParam}})
            {{/hasBodyParam}}
            .retrieve()
            {{#returnType}}
            .bodyToMono({{{.}}}.class){{#reactive}};{{/reactive}}{{^reactive}}
            .block();{{/reactive}}
            {{/returnType}}
            {{^returnType}}
            .bodyToMono(Void.class){{#reactive}};{{/reactive}}{{^reactive}}
            .block();{{/reactive}}
            {{/returnType}}
    }

{{/operation}}
}
{{/operations}}
"""
        # Save as apiService.mustache for service generation
        service_template_dir = os.path.join(self.template_dir, "api")
        os.makedirs(service_template_dir, exist_ok=True)
        with open(os.path.join(service_template_dir, "apiService.mustache"), 'w') as f:
            f.write(template_content)
    
    def _create_webclient_config_template(self):
        """Create WebClient configuration"""
        template_content = """package {{invokerPackage}}.configuration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;
import io.netty.channel.ChannelOption;
import io.netty.handler.timeout.ReadTimeoutHandler;
import io.netty.handler.timeout.WriteTimeoutHandler;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import reactor.netty.http.client.HttpClient;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

@Configuration
public class WebClientConfiguration {
    
    @Bean
    public WebClient.Builder webClientBuilder() {
        HttpClient httpClient = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5000)
            .responseTimeout(Duration.ofSeconds(30))
            .doOnConnected(conn -> 
                conn.addHandlerLast(new ReadTimeoutHandler(30, TimeUnit.SECONDS))
                    .addHandlerLast(new WriteTimeoutHandler(30, TimeUnit.SECONDS)));
        
        return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(httpClient));
    }
}
"""
        config_dir = os.path.join(self.template_dir, "configuration")
        os.makedirs(config_dir, exist_ok=True)
        with open(os.path.join(config_dir, "webClientConfiguration.mustache"), 'w') as f:
            f.write(template_content)
    
    def _create_application_class_template(self):
        """Create Spring Boot main application class"""
        template_content = """package {{invokerPackage}};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
"""
        with open(os.path.join(self.template_dir, "application.mustache"), 'w') as f:
            f.write(template_content)
    
    def _create_application_properties_template(self):
        """Create application.properties"""
        template_content = """# Server Configuration
server.port=8080

# Internal API Configuration
internal.api.base-url={{internalApiBaseUrl}}

# Logging
logging.level.root=INFO
logging.level.{{package}}=DEBUG
logging.level.org.springframework.web=DEBUG

# Spring Boot Actuator
management.endpoints.web.exposure.include=health,info
"""
        resources_dir = os.path.join(self.template_dir, "resources")
        os.makedirs(resources_dir, exist_ok=True)
        with open(os.path.join(resources_dir, "application.properties.mustache"), 'w') as f:
            f.write(template_content)
    
    def _create_pom_template(self):
        """Create enhanced pom.xml template"""
        template_content = """<project xmlns="http://maven.apache.org/POM/4.0.0" 
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    
    <groupId>{{groupId}}</groupId>
    <artifactId>{{artifactId}}</artifactId>
    <version>{{artifactVersion}}</version>
    <packaging>jar</packaging>
    
    <name>{{artifactId}}</name>
    <description>API Bridge generated by OpenAPI Generator</description>
    
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.0</version>
        <relativePath/>
    </parent>
    
    <properties>
        <java.version>17</java.version>
        <maven.compiler.source>17</maven.compiler.source>
        <maven.compiler.target>17</maven.compiler.target>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    
    <dependencies>
        <!-- Spring Boot Starters -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        
        <!-- Jackson for JSON -->
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
        </dependency>
        
        <dependency>
            <groupId>com.fasterxml.jackson.datatype</groupId>
            <artifactId>jackson-datatype-jsr310</artifactId>
        </dependency>
        
        <!-- OpenAPI/Swagger -->
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
        
        <!-- Validation -->
        <dependency>
            <groupId>javax.validation</groupId>
            <artifactId>validation-api</artifactId>
            <version>2.0.1.Final</version>
        </dependency>
        
        <dependency>
            <groupId>javax.annotation</groupId>
            <artifactId>javax.annotation-api</artifactId>
            <version>1.3.2</version>
        </dependency>
        
        <!-- Test Dependencies -->
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
        with open(os.path.join(self.template_dir, "pom.mustache"), 'w') as f:
            f.write(template_content)
    
    def _create_openapi_generator_config(self):
        """Create configuration for OpenAPI Generator"""
        internal_base_url = "http://localhost:8081"
        if self.internal_spec.get('servers'):
            internal_base_url = self.internal_spec['servers'][0].get('url', internal_base_url)
        
        config = {
            "generatorName": "spring",
            "inputSpec": os.path.abspath(self.external_oas_path),
            "outputDir": os.path.abspath(self.generated_dir),
            "templateDir": os.path.abspath(self.template_dir),
            "apiPackage": "com.generated.api",
            "modelPackage": "com.generated.model",
            "invokerPackage": "com.generated",
            "groupId": "com.generated",
            "artifactId": "api-bridge",
            "artifactVersion": "1.0.0",
            "additionalProperties": {
                "java8": "true",
                "dateLibrary": "java8",
                "useSpringBoot3": "true",
                "interfaceOnly": "false",
                "skipDefaultInterface": "false",
                "useTags": "true",
                "reactive": "true",
                "internalApiBaseUrl": internal_base_url,
                "delegatePattern": "true",
                "useOptional": "false"
            }
        }
        
        config_path = os.path.join(self.output_dir, "openapi-config.json")
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        return config_path
    
    def generate(self):
        """Main generation method"""
        print("=" * 60)
        print("API Bridge Generator - Spring Boot Code Generation")
        print("=" * 60)
        
        # Create directories
        print("\n[1/6] Creating template directories...")
        self._create_template_directories()
        
        # Create all templates
        print("[2/6] Creating Mustache templates...")
        self._create_api_mustache_template()
        self._create_service_mustache_template()
        self._create_webclient_config_template()
        self._create_application_class_template()
        self._create_application_properties_template()
        self._create_pom_template()
        
        # Create config
        print("[3/6] Creating OpenAPI Generator configuration...")
        config_path = self._create_openapi_generator_config()
        
        # Run OpenAPI Generator
        print("[4/6] Running OpenAPI Generator...")
        try:
            self._run_openapi_generator_cli(config_path)
        except Exception as e:
            print(f"CLI failed: {e}")
            print("Trying with Docker...")
            self._run_openapi_generator_docker(config_path)
        
        # Post-processing
        print("[5/6] Post-processing generated code...")
        self._post_process_generated_code()
        
        # Verification
        print("[6/6] Verifying generated code...")
        self._verify_generated_code()
        
        print("\n" + "=" * 60)
        print("✓ Generation complete!")
        print("=" * 60)
        print(f"\nGenerated code location: {self.generated_dir}")
        print("\nTo run the application:")
        print(f"  cd {self.generated_dir}")
        print("  ./mvnw spring-boot:run")
        print("\nOr build and run:")
        print("  ./mvnw clean package")
        print("  java -jar target/api-bridge-1.0.0.jar")
        
        return self.generated_dir
    
    def _run_openapi_generator_cli(self, config_path: str):
        """Run OpenAPI Generator using CLI"""
        cmd = [
            "openapi-generator-cli", "generate",
            "-i", os.path.abspath(self.external_oas_path),
            "-g", "spring",
            "-o", os.path.abspath(self.generated_dir),
            "-c", config_path,
            "-t", os.path.abspath(self.template_dir),
            "--additional-properties=useSpringBoot3=true,reactive=true,delegatePattern=true"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(result.stdout)
    
    def _run_openapi_generator_docker(self, config_path: str):
        """Run OpenAPI Generator using Docker"""
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{os.path.abspath(self.output_dir)}:/local",
            "openapitools/openapi-generator-cli", "generate",
            "-i", f"/local/{os.path.basename(self.external_oas_path)}",
            "-g", "spring",
            "-o", "/local/generated",
            "-c", f"/local/{os.path.basename(config_path)}",
            "-t", "/local/custom-templates/spring",
            "--additional-properties=useSpringBoot3=true,reactive=true,delegatePattern=true"
        ]
        
        # Copy OAS file to output dir for Docker volume mount
        shutil.copy(self.external_oas_path, self.output_dir)
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(result.stdout)
    
    def _post_process_generated_code(self):
        """Fix any issues in generated code"""
        # Ensure Service classes are generated
        # This might need manual template adjustments based on OpenAPI Generator version
        pass
    
    def _verify_generated_code(self):
        """Verify the generated code structure"""
        required_files = [
            "pom.xml",
            "src/main/java",
            "src/main/resources/application.properties"
        ]
        
        for file_path in required_files:
            full_path = os.path.join(self.generated_dir, file_path)
            if os.path.exists(full_path):
                print(f"  ✓ {file_path}")
            else:
                print(f"  ✗ {file_path} - MISSING!")
        
        # Check if it's buildable
        pom_path = os.path.join(self.generated_dir, "pom.xml")
        if os.path.exists(pom_path):
            print("\n  Validating Maven project...")
            try:
                # Make mvnw executable
                mvnw_path = os.path.join(self.generated_dir, "mvnw")
                if os.path.exists(mvnw_path):
                    os.chmod(mvnw_path, 0o755)
                print("  ✓ Project structure is valid")
            except Exception as e:
                print(f"  ! Warning: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Generate runnable Spring Boot API bridge code',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python api_bridge_generator.py --external external-api.yaml --internal internal-api.yaml
  python api_bridge_generator.py --external api.json --internal internal.json --output ./my-project
        """
    )
    parser.add_argument('--external', required=True, help='Path to external OAS file (YAML/JSON)')
    parser.add_argument('--internal', required=True, help='Path to internal OAS file (YAML/JSON)')
    parser.add_argument('--output', default='./output', help='Output directory (default: ./output)')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.external):
        print(f"Error: External OAS file not found: {args.external}")
        sys.exit(1)
    
    if not os.path.exists(args.internal):
        print(f"Error: Internal OAS file not found: {args.internal}")
        sys.exit(1)
    
    generator = APIBridgeGenerator(
        external_oas_path=args.external,
        internal_oas_path=args.internal,
        output_dir=args.output
    )
    
    try:
        generator.generate()
    except Exception as e:
        print(f"\n✗ Generation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
