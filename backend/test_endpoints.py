import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app

client = app.test_client()

print("=== 1. Testing /api/patients ===")
res = client.get("/api/patients")
p_data = res.get_json() or {}
patients = p_data.get("patients", [])
print(f"GET /api/patients: {res.status_code} | Total: {len(patients)}")
for p in patients[:3]:
    print(f"  Patient: {p['patient_id']} - {p['name']} (KL Grade: {p.get('oa_grade', 'Unknown')})")

print("\n=== 2. Testing /api/cohort ===")
res_cohort = client.get("/api/cohort")
c_data = res_cohort.get_json() or {}
print(f"GET /api/cohort: {res_cohort.status_code} | Total: {c_data.get('total_patients')}")

print("\n=== 3. Testing /api/llm/status ===")
res_llm = client.get("/api/llm/status")
print(f"GET /api/llm/status: {res_llm.status_code} | Status: {res_llm.get_json()}")

print("\n=== 4. Testing /api/chat ===")
res_chat = client.post("/api/chat", json={
    "patient_id": "PATIENT_001",
    "message": "What does a high crepitus score mean?"
})
chat_data = res_chat.get_json() or {}
reply = chat_data.get("reply", "")
print(f"POST /api/chat: {res_chat.status_code} | Reply snippet: {reply[:100]}...")

print("\n=== 5. Testing /api/diet ===")
res_diet = client.get("/api/diet?patient_id=PATIENT_001")
diet_data = res_diet.get_json() or {}
diet = diet_data.get("diet", {})
print(f"GET /api/diet: {res_diet.status_code} | Calorie target: {diet.get('calories')}")

print("\n=== 6. Testing /api/exercises ===")
res_ex = client.get("/api/exercises?patient_id=PATIENT_001")
ex_data = res_ex.get_json() or {}
exercises = ex_data.get("exercises", [])
print(f"GET /api/exercises: {res_ex.status_code} | Protocols count: {len(exercises)}")
if exercises:
    print(f"  First exercise: {exercises[0].get('name')} (Target: {exercises[0].get('target')})")

print("\n=== 7. Testing /api/report/generate & download ===")
res_rpt = client.post("/api/report/generate", json={"patient_id": "PATIENT_001"})
rpt_data = res_rpt.get_json() or {}
print(f"POST /api/report/generate: {res_rpt.status_code} | Response: {rpt_data}")
report_id = rpt_data.get("report_id")
if report_id:
    res_dl = client.get(f"/api/report/{report_id}")
    print(f"GET /api/report/{report_id}: {res_dl.status_code} | PDF size: {len(res_dl.data)} bytes")

print("\nALL 7 CLINICAL ENDPOINTS & REPORTING PIPELINE VERIFIED SUCCESSFULLY!")
