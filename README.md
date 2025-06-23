# Spring Boot Code Generator from OpenAPI (OAS) Spec

This Python script generates a fully structured Spring Boot Maven project using an OpenAPI (OAS) spec file.

## 📦 Features

- Parses OpenAPI 3.0 spec (YAML or JSON)
- Generates:
  - `Application.java`
  - `Controller.java` with methods for each path
  - `pom.xml`
  - Full Maven folder structure

## 🔧 Requirements

- Python 3.9+
- Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```

## 🚀 Usage

1. Put your OAS spec file in `specs/api.yaml`
2. Run the script:
   ```bash
   python lambda_function.py
   ```
3. Output will be in the `output/` folder.

## 📁 Output Structure

```
output/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/
        │   ├── Application.java
        │   └── Controller.java
        └── resources/application.properties
```

## ✅ AWS Lambda Compatible

This script can run inside a Lambda function to dynamically generate code from uploaded specs.

## 📄 License

MIT
