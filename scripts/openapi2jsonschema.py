"""Convert CRD manifests on stdin into kubeconform JSON schemas.

Usage: helm template ... --include-crds | python scripts/openapi2jsonschema.py <out-dir>
Files are written as <out-dir>/<group>/<kind lowercase>_<version>.json, the layout
kubeconform expects with -schema-location '<dir>/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'.
"""

import json
import sys
from pathlib import Path

import yaml


def main(out_dir: Path) -> int:
    written = 0
    for doc in yaml.safe_load_all(sys.stdin):
        if not doc or doc.get("kind") != "CustomResourceDefinition":
            continue
        spec = doc["spec"]
        group = spec["group"]
        kind = spec["names"]["kind"].lower()
        for version in spec.get("versions", []):
            schema = version.get("schema", {}).get("openAPIV3Schema")
            if not schema:
                continue
            schema = dict(schema)
            schema["$schema"] = "http://json-schema.org/schema#"
            target = out_dir / group
            target.mkdir(parents=True, exist_ok=True)
            (target / f"{kind}_{version['name']}.json").write_text(
                json.dumps(schema, indent=2)
            )
            written += 1
    if written == 0:
        print(
            f"error: wrote 0 schemas to {out_dir} (empty or non-CRD input)",
            file=sys.stderr,
        )
        return 1
    print(f"wrote {written} schema(s) to {out_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
