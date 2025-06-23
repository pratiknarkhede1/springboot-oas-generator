import os
from prance import ResolvingParser
from jinja2 import Environment, FileSystemLoader

BASE_DIR = os.path.dirname(__file__)
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
PACKAGE_PATH = os.path.join('com', 'example')
JAVA_OUT_DIR = os.path.join(OUTPUT_DIR, 'src', 'main', 'java', PACKAGE_PATH)
RES_OUT_DIR = os.path.join(OUTPUT_DIR, 'src', 'main', 'resources')

def parse_openapi_spec(spec_path):
    parser = ResolvingParser(spec_path)
    return parser.specification

def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

def generate_code(spec):
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

    # Application.java
    app_template = env.get_template("Application.java.j2")
    app_code = app_template.render(package="com.example", spec=spec)
    write_file(os.path.join(JAVA_OUT_DIR, "Application.java"), app_code)

    # Controller.java
    ctrl_template = env.get_template("Controller.java.j2")
    ctrl_code = ctrl_template.render(package="com.example", endpoints=spec["paths"])
    write_file(os.path.join(JAVA_OUT_DIR, "Controller.java"), ctrl_code)

    # pom.xml
    pom_template = env.get_template("pom.xml.j2")
    pom_code = pom_template.render()
    write_file(os.path.join(OUTPUT_DIR, "pom.xml"), pom_code)

    # application.properties
    write_file(os.path.join(RES_OUT_DIR, "application.properties"), "")

def lambda_handler(event=None, context=None):
    spec_path = os.path.join(BASE_DIR, 'specs', 'api.yaml')
    spec = parse_openapi_spec(spec_path)
    generate_code(spec)
    return {"status": "Spring Boot project generated"}
