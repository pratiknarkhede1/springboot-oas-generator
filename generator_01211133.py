# oas_gateway_generator.py

import yaml
import os
from pathlib import Path
from litellm import completion
from typing import Dict, List, Optional
import json

class SpringBootGatewayGenerator:
    def __init__(self, external_oas_file: str, internal_oas_file: str, internal_base_url: str):
        """
        Initialize the generator with external and internal OAS files
        
        Args:
            external_oas_file: Path to external API specification
            internal_oas_file: Path to internal API specification
            internal_base_url: Base URL for internal API (e.g., http://internal-service:8080)
        """
        with open(external_oas_file, 'r') as f:
            self.external_spec = yaml.safe_load(f)
            self.external_yaml = f.read()
            
        with open(internal_oas_file, 'r') as f:
            self.internal_spec = yaml.safe_load(f)
            self.internal_yaml = f.read()
            
        self.internal_base_url = internal_base_url
        self.project_name = self.external_spec['info']['title'].replace(' ', '').replace('-', '')
        self.base_package = f"com.gateway.{self.project_name.lower()}"
        
    def map_endpoints(self) -> List[Dict]:
        """
        Map external endpoints to internal endpoints based on path and operation
        """
        mappings = []
        
        for ext_path, ext_methods in self.external_spec.get('paths', {}).items():
            for ext_method, ext_details in ext_methods.items():
                if ext_method not in ['get', 'post', 'put', 'delete', 'patch']:
                    continue
                
                # Try to find matching internal endpoint
                # Strategy: look for similar paths or use operationId mapping
                internal_mapping = self._find_internal_endpoint(ext_path, ext_method, ext_details)
                
                if internal_mapping:
                    mappings.append({
                        'external_path': ext_path,
                        'external_method': ext_method,
                        'external_details': ext_details,
                        'internal_path': internal_mapping['path'],
                        'internal_method': internal_mapping['method'],
                        'internal_details': internal_mapping['details']
                    })
        
        return mappings
    
    def _find_internal_endpoint(self, ext_path: str, ext_method: str, ext_details: Dict) -> Optional[Dict]:
        """
        Find matching internal endpoint for an external endpoint
        """
        # First try: exact path match
        if ext_path in self.internal_spec.get('paths', {}):
            if ext_method in self.internal_spec['paths'][ext_path]:
                return {
                    'path': ext_path,
                    'method': ext_method,
                    'details': self.internal_spec['paths'][ext_path][ext_method]
                }
        
        # Second try: similar path (remove version prefixes, etc.)
        for int_path, int_methods in self.internal_spec.get('paths', {}).items():
            if self._paths_similar(ext_path, int_path):
                if ext_method in int_methods:
                    return {
                        'path': int_path,
                        'method': ext_method,
                        'details': int_methods[ext_method]
                    }
        
        # Third try: use operationId or tags matching
        ext_op_id = ext_details.get('operationId', '')
        for int_path, int_methods in self.internal_spec.get('paths', {}).items():
            for int_method, int_details in int_methods.items():
                if int_method not in ['get', 'post', 'put', 'delete', 'patch']:
                    continue
                int_op_id = int_details.get('operationId', '')
                if ext_op_id and int_op_id and ext_op_id.lower() == int_op_id.lower():
                    return {
                        'path': int_path,
                        'method': int_method,
                        'details': int_details
                    }
        
        return None
    
    def _paths_similar(self, path1: str, path2: str) -> bool:
        """Check if two paths are similar (ignoring version prefixes)"""
        # Remove common prefixes like /v1, /api, etc.
        clean1 = path1.replace('/v1', '').replace('/v2', '').replace('/api', '')
        clean2 = path2.replace('/v1', '').replace('/v2', '').replace('/api', '')
        return clean1 == clean2
    
    def generate_project(self, output_dir: str = "generated-gateway"):
        """Generate complete Spring Boot 3 project"""
        mappings = self.map_endpoints()
        
        print(f"Found {len(mappings)} endpoint mappings")
        
        # Create directory structure
        self._create_directory_structure(output_dir)
        
        # Generate files
        self._generate_pom_xml(output_dir)
        self._generate_application_properties(output_dir)
        self._generate_main_class(output_dir)
        self._generate_models(output_dir, mappings)
        self._generate_controllers(output_dir, mappings)
        self._generate_services(output_dir, mappings)
        self._generate_client_config(output_dir)
        self._generate_exception_handler(output_dir)
        self._generate_tests(output_dir, mappings)
        self._generate_readme(output_dir)
        self._generate_dockerfile(output_dir)
        
        print(f"\n✅ Project generated successfully in: {output_dir}")
        print(f"📦 Base package: {self.base_package}")
        print(f"🚀 To run: cd {output_dir} && ./mvnw spring-boot:run")
    
    def _create_directory_structure(self, output_dir: str):
        """Create Maven project directory structure"""
        base_path = Path(output_dir)
        
        # Maven structure
        src_main = base_path / "src" / "main"
        src_test = base_path / "src" / "test"
        
        # Java packages
        package_path = self.base_package.replace('.', '/')
        
        dirs = [
            src_main / "java" / package_path / "controller",
            src_main / "java" / package_path / "service",
            src_main / "java" / package_path / "model" / "request",
            src_main / "java" / package_path / "model" / "response",
            src_main / "java" / package_path / "config",
            src_main / "java" / package_path / "exception",
            src_main / "java" / package_path / "client",
            src_main / "resources",
            src_test / "java" / package_path / "controller",
            src_test / "java" / package_path / "service",
        ]
        
        for dir_path in dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    def _generate_pom_xml(self, output_dir: str):
        """Generate pom.xml using LLM"""
        prompt = f"""Generate a complete pom.xml for a Spring Boot 3.2.x project with Java 21.

Project details:
- Group ID: com.gateway
- Artifact ID: {self.project_name.lower()}-gateway
- Name: {self.project_name} Gateway
- Description: Gateway service exposing external APIs and calling internal services

Required dependencies:
- Spring Boot Starter Web
- Spring Boot Starter WebFlux (for WebClient)
- Spring Boot Starter Validation
- Spring Boot Starter Actuator
- Lombok
- SpringDoc OpenAPI (for Swagger UI)
- Spring Boot Starter Test
- Micrometer for metrics

Include:
- Java 21 configuration
- Spring Boot 3.2.x parent
- Maven compiler plugin for Java 21
- Spring Boot Maven plugin

Provide ONLY the pom.xml content, no explanations."""

        response = completion(
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": prompt}]
        )
        
        content = self._extract_code(response.choices[0].message.content)
        
        with open(f"{output_dir}/pom.xml", 'w') as f:
            f.write(content)
        
        print("✓ Generated pom.xml")
    
    def _generate_application_properties(self, output_dir: str):
        """Generate application.properties"""
        content = f"""# Server Configuration
server.port=8080
spring.application.name={self.project_name.lower()}-gateway

# Internal Service Configuration
internal.service.base-url={self.internal_base_url}
internal.service.connect-timeout=5000
internal.service.read-timeout=10000

# Logging
logging.level.root=INFO
logging.level.{self.base_package}=DEBUG
logging.pattern.console=%d{{yyyy-MM-dd HH:mm:ss}} - %msg%n

# Actuator
management.endpoints.web.exposure.include=health,info,metrics
management.endpoint.health.show-details=always

# API Documentation
springdoc.api-docs.path=/api-docs
springdoc.swagger-ui.path=/swagger-ui.html
springdoc.swagger-ui.operationsSorter=method
"""
        
        path = Path(output_dir) / "src" / "main" / "resources" / "application.properties"
        with open(path, 'w') as f:
            f.write(content)
        
        print("✓ Generated application.properties")
    
    def _generate_main_class(self, output_dir: str):
        """Generate Spring Boot main application class"""
        class_name = f"{self.project_name}GatewayApplication"
        
        content = f"""package {self.base_package};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class {class_name} {{

    public static void main(String[] args) {{
        SpringApplication.run({class_name}.class, args);
    }}
}}
"""
        
        package_path = self.base_package.replace('.', '/')
        path = Path(output_dir) / "src" / "main" / "java" / package_path / f"{class_name}.java"
        with open(path, 'w') as f:
            f.write(content)
        
        print(f"✓ Generated {class_name}.java")
    
    def _generate_models(self, output_dir: str, mappings: List[Dict]):
        """Generate model classes using LLM"""
        # Extract all schemas from both specs
        external_schemas = self.external_spec.get('components', {}).get('schemas', {})
        internal_schemas = self.internal_spec.get('components', {}).get('schemas', {})
        
        if not external_schemas and not internal_schemas:
            print("⚠ No schemas found, skipping model generation")
            return
        
        prompt = f"""Generate Java 21 record classes for these OpenAPI schemas.

External API Schemas (these will be exposed):
```yaml
{yaml.dump(external_schemas)}
```

Internal API Schemas (for reference):
```yaml
{yaml.dump(internal_schemas)}
```

Requirements:
- Use Java 21 records for immutable DTOs
- Use appropriate Jakarta validation annotations (@NotNull, @NotBlank, @Size, etc.)
- Use Jackson annotations where needed
- Generate separate request and response models
- Package: {self.base_package}.model.request for requests
- Package: {self.base_package}.model.response for responses
- Include proper imports
- Add Javadoc comments

Generate each class separately with a header comment showing the filename.
Format: // File: ModelName.java"""

        response = completion(
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        
        content = response.choices[0].message.content
        self._save_multiple_java_files(output_dir, content)
        
        print("✓ Generated model classes")
    
    def _generate_controllers(self, output_dir: str, mappings: List[Dict]):
        """Generate REST controllers using LLM"""
        mappings_info = self._format_mappings_for_llm(mappings)
        
        prompt = f"""Generate Spring Boot 3 REST controllers for this gateway service.

External API Specification:
```yaml
{self.external_yaml}
```

Endpoint Mappings (External -> Internal):
```json
{json.dumps(mappings_info, indent=2)}
```

Requirements:
- Use Spring Boot 3 and Java 21
- Package: {self.base_package}.controller
- Create separate controllers for different resource types
- Use @RestController and @RequestMapping
- Use appropriate HTTP method annotations (@GetMapping, @PostMapping, etc.)
- Include @Valid for request validation
- Inject and use corresponding service classes
- Include proper error handling
- Add Swagger/OpenAPI annotations (@Operation, @ApiResponse)
- Add logging
- Return ResponseEntity with appropriate status codes
- Extract path variables and query parameters correctly
- Handle request bodies properly

Generate each controller class separately with a header comment showing the filename.
Format: // File: ControllerName.java"""

        response = completion(
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        
        content = response.choices[0].message.content
        self._save_multiple_java_files(output_dir, content)
        
        print("✓ Generated controller classes")
    
    def _generate_services(self, output_dir: str, mappings: List[Dict]):
        """Generate service layer using LLM"""
        mappings_info = self._format_mappings_for_llm(mappings)
        
        prompt = f"""Generate Spring Boot 3 service classes that call internal APIs.

Internal API Specification:
```yaml
{self.internal_yaml}
```

Endpoint Mappings (External -> Internal):
```json
{json.dumps(mappings_info, indent=2)}
```

Internal Service Base URL: {self.internal_base_url}

Requirements:
- Use Spring Boot 3 and Java 21
- Package: {self.base_package}.service
- Use @Service annotation
- Inject WebClient for making HTTP calls to internal service
- Create methods that map external requests to internal API calls
- Handle path parameters, query parameters, and request bodies
- Include proper error handling and logging
- Use proper HTTP methods (GET, POST, PUT, DELETE)
- Map responses from internal API to external response models
- Add retry logic for transient failures
- Include timeout handling
- Use SLF4J for logging

Generate each service class separately with a header comment showing the filename.
Format: // File: ServiceName.java

Also generate a WebClient configuration class:
- File: WebClientConfig.java
- Package: {self.base_package}.config
- Configure WebClient bean with timeouts and base URL from properties"""

        response = completion(
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        
        content = response.choices[0].message.content
        self._save_multiple_java_files(output_dir, content)
        
        print("✓ Generated service classes and WebClient config")
    
    def _generate_client_config(self, output_dir: str):
        """Generate REST client configuration"""
        content = f"""package {self.base_package}.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

import java.time.Duration;

@Configuration
public class WebClientConfig {{

    @Value("${{internal.service.base-url}}")
    private String baseUrl;

    @Value("${{internal.service.connect-timeout:5000}}")
    private int connectTimeout;

    @Value("${{internal.service.read-timeout:10000}}")
    private int readTimeout;

    @Bean
    public WebClient internalServiceWebClient() {{
        ConnectionProvider connectionProvider = ConnectionProvider.builder("internal-service-pool")
                .maxConnections(100)
                .pendingAcquireTimeout(Duration.ofSeconds(45))
                .build();

        HttpClient httpClient = HttpClient.create(connectionProvider)
                .responseTimeout(Duration.ofMillis(readTimeout))
                .option(io.netty.channel.ChannelOption.CONNECT_TIMEOUT_MILLIS, connectTimeout);

        return WebClient.builder()
                .baseUrl(baseUrl)
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }}
}}
"""
        
        package_path = self.base_package.replace('.', '/')
        path = Path(output_dir) / "src" / "main" / "java" / package_path / "config" / "WebClientConfig.java"
        with open(path, 'w') as f:
            f.write(content)
        
        print("✓ Generated WebClientConfig.java")
    
    def _generate_exception_handler(self, output_dir: str):
        """Generate global exception handler"""
        prompt = f"""Generate a global exception handler for a Spring Boot 3 gateway application.

Requirements:
- Package: {self.base_package}.exception
- Create custom exception classes for common scenarios
- Create @RestControllerAdvice class
- Handle WebClient exceptions (4xx, 5xx from internal service)
- Handle validation errors
- Handle generic exceptions
- Return proper error response format with timestamp, status, message, path
- Log errors appropriately
- Use Java 21 and Spring Boot 3

Generate:
1. ErrorResponse.java - record class for error responses
2. Custom exception classes (InternalServiceException, ResourceNotFoundException, etc.)
3. GlobalExceptionHandler.java - @RestControllerAdvice class

Format each file with: // File: ClassName.java"""

        response = completion(
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        
        content = response.choices[0].message.content
        self._save_multiple_java_files(output_dir, content)
        
        print("✓ Generated exception handler classes")
    
    def _generate_tests(self, output_dir: str, mappings: List[Dict]):
        """Generate test classes"""
        if not mappings:
            print("⚠ No mappings found, skipping test generation")
            return
            
        # Pick first mapping as example
        example_mapping = mappings[0]
        
        prompt = f"""Generate JUnit 5 tests for a Spring Boot 3 gateway controller.

Example endpoint mapping:
- External: {example_mapping['external_method'].upper()} {example_mapping['external_path']}
- Internal: {example_mapping['internal_method'].upper()} {example_mapping['internal_path']}

Requirements:
- Use JUnit 5 and Spring Boot Test
- Package: {self.base_package}.controller (for controller tests)
- Use @WebMvcTest for controller tests
- Mock the service layer with @MockBean
- Test successful responses
- Test error scenarios
- Use MockMvc for HTTP requests
- Assert response status and body
- Java 21 and Spring Boot 3

Generate a sample controller test class.
Format: // File: ControllerNameTest.java"""

        response = completion(
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        
        content = response.choices[0].message.content
        self._save_multiple_java_files(output_dir, content, is_test=True)
        
        print("✓ Generated test classes")
    
    def _generate_readme(self, output_dir: str):
        """Generate README.md"""
        mappings = self.map_endpoints()
        endpoints_table = self._format_endpoints_table(mappings)
        
        content = f"""# {self.project_name} Gateway Service

API Gateway service that exposes external APIs and proxies requests to internal services.

## Overview

This Spring Boot 3 application acts as a gateway between external clients and internal microservices.

**Technology Stack:**
- Java 21
- Spring Boot 3.2.x
- Spring WebFlux (WebClient for internal calls)
- Maven
- OpenAPI/Swagger

## Architecture
```
External Client -> Gateway Service -> Internal Service
                   (this app)         ({self.internal_base_url})
```

## API Endpoints

{endpoints_table}

## Configuration

Edit `src/main/resources/application.properties`:
```properties
# Internal service URL
internal.service.base-url={self.internal_base_url}

# Timeouts
internal.service.connect-timeout=5000
internal.service.read-timeout=10000

# Server port
server.port=8080
```

## Running the Application

### Prerequisites
- Java 21
- Maven 3.9+

### Build and Run
```bash
# Build
./mvnw clean package

# Run
./mvnw spring-boot:run

# Or run the JAR
java -jar target/{self.project_name.lower()}-gateway-1.0.0.jar
```

### Docker
```bash
# Build image
docker build -t {self.project_name.lower()}-gateway .

# Run container
docker run -p 8080:8080 \\
  -e INTERNAL_SERVICE_BASE_URL={self.internal_base_url} \\
  {self.project_name.lower()}-gateway
```

## API Documentation

Once running, access Swagger UI at:
- http://localhost:8080/swagger-ui.html

OpenAPI spec available at:
- http://localhost:8080/api-docs

## Health Check
```bash
curl http://localhost:8080/actuator/health
```

## Development

### Project Structure
```
src/
├── main/
│   ├── java/
│   │   └── {self.base_package.replace('.', '/')}/
│   │       ├── controller/     # REST controllers
│   │       ├── service/        # Business logic & internal API calls
│   │       ├── model/          # Request/Response DTOs
│   │       ├── config/         # Configuration classes
│   │       ├── exception/      # Exception handling
│   │       └── client/         # Internal API clients
│   └── resources/
│       └── application.properties
└── test/
    └── java/                   # Unit tests
```

### Running Tests
```bash
./mvnw test
```

### Code Generation

This project was generated using the OAS Gateway Generator.

**Source Specifications:**
- External API: Based on external OpenAPI specification
- Internal API: Based on internal OpenAPI specification

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `INTERNAL_SERVICE_BASE_URL` | Internal service base URL | `{self.internal_base_url}` |
| `SERVER_PORT` | Application port | `8080` |
| `SPRING_PROFILES_ACTIVE` | Active Spring profile | - |

## Monitoring

Access actuator endpoints:
- Health: http://localhost:8080/actuator/health
- Metrics: http://localhost:8080/actuator/metrics
- Info: http://localhost:8080/actuator/info

## License

[Your License Here]

## Support

For issues or questions, please contact [Your Contact Info]
"""
        
        with open(f"{output_dir}/README.md", 'w') as f:
            f.write(content)
        
        print("✓ Generated README.md")
    
    def _generate_dockerfile(self, output_dir: str):
        """Generate Dockerfile"""
        content = f"""# Multi-stage build for Spring Boot 3 with Java 21

# Build stage
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /app

# Copy pom and download dependencies (cached layer)
COPY pom.xml .
RUN mvn dependency:go-offline -B

# Copy source and build
COPY src ./src
RUN mvn clean package -DskipTests

# Runtime stage
FROM eclipse-temurin:21-jre-alpine
WORKDIR /app

# Create non-root user
RUN addgroup -S spring && adduser -S spring -G spring
USER spring:spring

# Copy JAR from build stage
COPY --from=build /app/target/*.jar app.jar

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \\
  CMD wget --quiet --tries=1 --spider http://localhost:8080/actuator/health || exit 1

# Run application
ENTRYPOINT ["java", "-jar", "app.jar"]
"""
        
        with open(f"{output_dir}/Dockerfile", 'w') as f:
            f.write(content)
        
        # Also generate .dockerignore
        dockerignore = """target/
.mvn/
*.iml
.idea/
.settings/
.classpath
.project
"""
        with open(f"{output_dir}/.dockerignore", 'w') as f:
            f.write(dockerignore)
        
        print("✓ Generated Dockerfile")
    
    def _format_mappings_for_llm(self, mappings: List[Dict]) -> List[Dict]:
        """Format mappings for LLM consumption"""
        formatted = []
        for m in mappings:
            formatted.append({
                'external': {
                    'method': m['external_method'].upper(),
                    'path': m['external_path'],
                    'operationId': m['external_details'].get('operationId', ''),
                    'parameters': m['external_details'].get('parameters', []),
                    'requestBody': m['external_details'].get('requestBody', {}),
                    'responses': m['external_details'].get('responses', {})
                },
                'internal': {
                    'method': m['internal_method'].upper(),
                    'path': m['internal_path'],
                    'operationId': m['internal_details'].get('operationId', ''),
                    'parameters': m['internal_details'].get('parameters', []),
                    'requestBody': m['internal_details'].get('requestBody', {}),
                    'responses': m['internal_details'].get('responses', {})
                }
            })
        return formatted
    
    def _format_endpoints_table(self, mappings: List[Dict]) -> str:
        """Format endpoint mappings as markdown table"""
        if not mappings:
            return "No endpoint mappings found."
        
        table = "| External Endpoint | Internal Endpoint |\n"
        table += "|-------------------|-------------------|\n"
        
        for m in mappings:
            ext = f"`{m['external_method'].upper()} {m['external_path']}`"
            int_ep = f"`{m['internal_method'].upper()} {m['internal_path']}`"
            table += f"| {ext} | {int_ep} |\n"
        
        return table
    
    def _extract_code(self, content: str) -> str:
        """Extract code from markdown code blocks"""
        if '```xml' in content:
            start = content.find('```xml') + 6
            end = content.find('```', start)
            return content[start:end].strip()
        elif '```' in content:
            start = content.find('```') + 3
            # Skip language identifier
            newline = content.find('\n', start)
            start = newline + 1 if newline != -1 else start
            end = content.find('```', start)
            return content[start:end].strip()
        return content.strip()
    
    def _save_multiple_java_files(self, output_dir: str, content: str, is_test: bool = False):
        """Parse and save multiple Java files from LLM output"""
        # Split by file markers
        files = content.split('// File: ')
        
        for file_content in files[1:]:  # Skip first empty split
            lines = file_content.split('\n')
            filename = lines[0].strip()
            
            # Extract code (skip markdown if present)
            code_lines = lines[1:]
            code = '\n'.join(code_lines)
            
            # Remove markdown code blocks if present
            if '```java' in code:
                code = self._extract_code(code)
            elif '```' in code:
                code = self._extract_code(code)
            
            # Determine package from content
            package_line = [l for l in code.split('\n') if l.strip().startswith('package ')]
            if not package_line:
                print(f"⚠ Skipping {filename} - no package declaration found")
                continue
            
            package = package_line[0].replace('package ', '').replace(';', '').strip()
            package_path = package.replace('.', '/')
            
            # Determine subdirectory based on package
            if is_test:
                base_dir = Path(output_dir) / "src" / "test" / "java"
            else:
                base_dir = Path(output_dir) / "src" / "main" / "java"
            
            file_path = base_dir / package_path / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w') as f:
                f.write(code)
            
            print(f"  ✓ Generated {filename}")


# Example usage and sample OAS files
def create_sample_oas_files():
    """Create sample OAS files for testing"""
    
    external_oas = """
openapi: 3.0.0
info:
  title: Pet Store External API
  version: 1.0.0
  description: Public-facing Pet Store API
paths:
  /api/v1/pets:
    get:
      operationId: listPets
      summary: List all pets
      parameters:
        - name: limit
          in: query
          schema:
            type: integer
            default: 20
      responses:
        '200':
          description: List of pets
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Pet'
    post:
      operationId: createPet
      summary: Create a new pet
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/PetRequest'
      responses:
        '201':
          description: Pet created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Pet'
  /api/v1/pets/{petId}:
    get:
      operationId: getPet
      summary: Get pet by ID
      parameters:
        - name: petId
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        '200':
          description: Pet details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Pet'
        '404':
          description: Pet not found
components:
  schemas:
    Pet:
      type: object
      required:
        - id
        - name
      properties:
        id:
          type: integer
          format: int64
        name:
          type: string
        species:
          type: string
        age:
          type: integer
    PetRequest:
      type: object
      required:
        - name
      properties:
        name:
          type: string
          min
