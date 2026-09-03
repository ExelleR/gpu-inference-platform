import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "openapi2jsonschema.py"

CRD = """
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: widgets.example.io
spec:
  group: example.io
  names:
    kind: Widget
    plural: widgets
  scope: Namespaced
  versions:
    - name: v1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
"""


def test_writes_one_schema_per_version(tmp_path: Path) -> None:
    subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], input=CRD, text=True, check=True)
    out = tmp_path / "example.io" / "widget_v1.json"
    assert out.exists()
    schema = json.loads(out.read_text())
    assert schema["$schema"] == "http://json-schema.org/schema#"
    assert schema["properties"]["spec"]["type"] == "object"


def test_no_crd_input_fails(tmp_path: Path) -> None:
    non_crd = "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: x\n"
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], input=non_crd, text=True)
    assert result.returncode == 1
    assert list(tmp_path.iterdir()) == []
