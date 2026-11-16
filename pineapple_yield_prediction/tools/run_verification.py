"""In-process check of the prediction service against samples/sample_request.json."""

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from predict import app

client = TestClient(app)

health = client.get("/health").json()["status"]
request = json.loads((BASE / "samples" / "sample_request.json").read_text())
response = client.post("/predict", json=request).json()
expected = json.loads((BASE / "samples" / "sample_response.json").read_text())["yield_mt_ha"]

print()
print("Predict check")
print("=" * 20)
print(f"{'health':<12} {health}")
print(f"{'request':<12} samples/sample_request.json")
print(f"{'response':<12} {response['yield_mt_ha']:.2f} mt/ha")
print(f"{'expected':<12} {expected:.2f} mt/ha")
print(f"{'result':<12} {'PASS' if abs(response['yield_mt_ha'] - expected) < 1e-6 else 'FAIL'}")
