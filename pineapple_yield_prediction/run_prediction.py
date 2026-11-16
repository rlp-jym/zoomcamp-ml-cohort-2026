"""In-process check of the prediction service against sample_request.json."""

import json

from fastapi.testclient import TestClient

from predict import app

client = TestClient(app)

health = client.get("/health").json()["status"]
request = json.load(open("sample_request.json"))
response = client.post("/predict", json=request).json()
expected = json.load(open("sample_response.json"))["yield_mt_ha"]

print()
print("Predict check")
print("=" * 20)
print(f"{'health':<12} {health}")
print(f"{'request':<12} sample_request.json")
print(f"{'response':<12} {response['yield_mt_ha']:.2f} mt/ha")
print(f"{'expected':<12} {expected:.2f} mt/ha")
print(f"{'result':<12} {'PASS' if abs(response['yield_mt_ha'] - expected) < 1e-6 else 'FAIL'}")
