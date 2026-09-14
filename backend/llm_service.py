"""
=============================================================
 OA Detection System — LLM Clinical Insights Service
 SIH 2026 | Problem Statement 26004 | MDoNER
=============================================================
 Provides:
   - chat()                  → Gemini-powered clinical Q&A
   - generate_diet_plan()    → structured anti-inflammatory diet
   - generate_exercise_protocol() → rehab exercise cards
   - get_clinical_summary()  → narrative summary of patient data

 Falls back to rule-based engine if GEMINI_API_KEY is not set.
=============================================================
"""

import os
import json
import re

# ── Try to import Google Generative AI ────────────────────────────────────────
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

_model = None

def _get_model():
    global _model
    if _model is None and GEMINI_AVAILABLE and GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        _model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={"temperature": 0.6, "max_output_tokens": 1024},
            system_instruction=_SYSTEM_PROMPT
        )
    return _model


_SYSTEM_PROMPT = """You are an expert AI clinical assistant specialised in knee Osteoarthritis (OA) 
analysis for an IoT-based early detection system (SIH 2026, MDoNER, North Eastern India). 
You interpret real-time sensor data from an ESP32-S3 wearable device equipped with:
- INMP441 microphone (crepitus/joint sounds)
- MLX90614 IR temperature sensor
- MPU6050 6-axis IMU (gait & motion)
- Flex sensor (range of motion)

When given patient data, provide clinically accurate, evidence-based, compassionate responses.
Always emphasize that this is a screening tool, not a diagnostic replacement for orthopedic specialists.
Format your responses clearly with sections. Use simple language the patient can understand.
For diet and exercise recommendations, be specific and practical for Indian/Northeast Indian context.
Never provide definitive diagnoses. Always recommend professional consultation for HIGH/CRITICAL risk scores."""


# ─── CHAT ─────────────────────────────────────────────────────────────────────

def chat(patient_id: str, user_message: str, patient_context: dict) -> str:
    """
    Generate a clinical insights response for a doctor's/patient's question.
    patient_context: dict with keys: patient, latest_reading, trend_summary, risk_level
    """
    context_str = _format_context(patient_id, patient_context)
    full_prompt = f"{context_str}\n\nQuestion: {user_message}"

    model = _get_model()
    if model:
        try:
            response = model.generate_content(full_prompt)
            return response.text
        except Exception as e:
            print(f"[LLM] Gemini error: {e} — falling back to rule-based")

    # Rule-based fallback
    return _rule_based_chat(user_message, patient_context)


def _format_context(patient_id: str, ctx: dict) -> str:
    patient = ctx.get("patient", {})
    reading = ctx.get("latest_reading", {})
    trend   = ctx.get("trend_summary", {})
    risk    = reading.get("risk_score", 0)
    level   = reading.get("risk_level", "UNKNOWN")

    lines = [
        f"=== PATIENT CONTEXT ===",
        f"Patient ID: {patient_id}",
        f"Name: {patient.get('name', 'Unknown')}  Age: {patient.get('age', '?')}  Gender: {patient.get('gender', '?')}",
        f"BMI: {patient.get('bmi', '?')}  OA Grade (KL): {patient.get('oa_grade', 'Unknown')}",
        f"Comorbidities: {patient.get('comorbidities', 'None')}",
        f"",
        f"=== LATEST SENSOR READINGS ===",
        f"Risk Score: {risk:.1%} ({level})",
        f"Joint Temperature: {reading.get('joint_temp_c', '?')}°C  (Thermal Asymmetry: {reading.get('temp_asymmetry', '?')}°C)",
        f"Crepitus Score: {reading.get('crepitus_score', '?')} (Dominant Freq: {reading.get('dominant_freq_hz', '?')} Hz)",
        f"Flexion ROM: {reading.get('flex_angle_deg', '?')}°  Stiffness: {reading.get('flex_stiffness', '?')}",
        f"Gait Symmetry: {reading.get('step_symmetry', '?')}  Gyro ROM: {reading.get('gyro_range_deg', '?')}°",
        f"",
        f"=== TREND (7-DAY) ===",
        f"Trend direction: {trend.get('direction', 'Unknown')}  Slope: {trend.get('slope', 0):.4f}/day",
        f"===",
    ]
    return "\n".join(lines)


def _rule_based_chat(question: str, ctx: dict) -> str:
    reading = ctx.get("latest_reading", {})
    risk    = reading.get("risk_score", 0)
    level   = reading.get("risk_level", "LOW")
    rom     = reading.get("flex_angle_deg", 110)
    crep    = reading.get("crepitus_score", 0.05)
    temp    = reading.get("joint_temp_c", 33.2)

    q = question.lower()

    if any(w in q for w in ["risk", "score", "percentage", "how bad"]):
        return _risk_explanation(risk, level, rom, crep, temp)
    elif any(w in q for w in ["diet", "food", "eat", "nutrition", "meal"]):
        return _diet_summary(risk, level)
    elif any(w in q for w in ["exercise", "rehab", "physio", "therapy", "workout"]):
        return _exercise_summary(risk, rom)
    elif any(w in q for w in ["crepitus", "sound", "cracking", "clicking", "noise"]):
        return _crepitus_explanation(crep)
    elif any(w in q for w in ["temperature", "temp", "heat", "warm", "inflammation"]):
        return _temp_explanation(temp)
    elif any(w in q for w in ["gait", "walk", "symmetry", "step", "limp"]):
        sym = reading.get("step_symmetry", 0.9)
        return _gait_explanation(sym)
    else:
        return _general_response(risk, level)


def _risk_explanation(risk, level, rom, crep, temp):
    return f"""## OA Risk Assessment

**Current Risk Score: {risk:.1%} — {level}**

Your OA screening system has analyzed multiple biomarkers from the wearable sensors:

**Key contributing factors:**
- 🌡️ Joint temperature is {'elevated at' if temp > 34.5 else 'within normal range at'} {temp:.1f}°C (normal: 32–34°C), suggesting {'active synovial inflammation.' if temp > 34.5 else 'no significant inflammation currently.'}
- 🔊 Crepitus score is {crep:.2f} ({'high — abnormal joint sounds detected in the 300–800 Hz crepitus band.' if crep > 0.3 else 'low — minimal joint sound irregularities.'})
- 🦵 Flexion ROM is {rom:.0f}° ({'reduced — limited range of motion is a common OA indicator.' if rom < 90 else 'within acceptable range for daily function.'})

**Clinical interpretation:**
{"⚠️ HIGH/CRITICAL risk detected. We strongly recommend consulting an orthopedic specialist promptly. X-ray evaluation (KL grading) and physical examination are advisable." if risk >= 0.55 else "The current markers suggest early-stage changes. Regular monitoring and preventive measures are recommended."}

*This is a screening tool, not a clinical diagnosis.*"""


def _crepitus_explanation(crep):
    return f"""## Acoustic Crepitus Analysis

**Crepitus Score: {crep:.2f}** {'⚠️ (Elevated)' if crep > 0.3 else '✅ (Normal Range)'}

**What is crepitus?**
Crepitus refers to the crackling, grinding, or popping sounds made by joints during movement. In the knee, it results from:
- Roughened cartilage surfaces rubbing together
- Presence of small loose bodies within the joint
- Gas bubble release from synovial fluid

**What the sensor detects:**
The INMP441 microphone captures joint sounds during movement. Abnormal energy in the **300–800 Hz frequency band** is a validated crepitus marker.

**Current status:** {"The elevated crepitus score indicates significant cartilage surface irregularity, commonly associated with Grade 2+ OA." if crep > 0.3 else "Crepitus is within the normal physiological range. Some degree of joint sound is completely normal."}

*For definitive assessment, MRI or arthroscopic examination may be warranted.*"""


def _temp_explanation(temp):
    return f"""## Joint Temperature Analysis

**Current joint temperature: {temp:.1f}°C**

Normal knee surface temperature: **32.0 – 34.0°C**

{'⚠️ **Elevated temperature detected.** Joint hyperthermia is a reliable marker of synovial inflammation. In OA, degraded cartilage triggers inflammatory mediators (IL-1β, TNF-α) that increase local blood flow and heat production.' if temp > 34.5 else '✅ **Temperature within normal range.** No significant inflammatory activity detected from thermal markers.'}

**Clinical context:**
- Temperature asymmetry between knees >1°C is clinically significant
- Persistent warmth combined with other OA markers suggests active synovitis
- NSAIDs or topical anti-inflammatory gels may help reduce localized inflammation

*Please consult a rheumatologist or orthopedic surgeon for persistent joint warmth.*"""


def _gait_explanation(sym):
    return f"""## Gait Symmetry Analysis

**Step Symmetry Index: {sym:.2f}** (Normal: 0.90 – 1.00)

{'⚠️ **Asymmetric gait detected.** ' if sym < 0.85 else '✅ **Gait symmetry is acceptable.** '}

**What this means:**
Gait symmetry measures the balance between left and right limb loading during walking. A score below 0.85 suggests:
- **Antalgic gait** — compensating for joint pain
- Muscle weakness in the affected limb
- Altered weight distribution to protect the painful joint

**Implications for OA:**
Persistent asymmetric gait increases mechanical stress on the healthier joint, potentially accelerating bilateral OA progression.

**Recommended action:**
{f'Physiotherapy focusing on quadriceps strengthening and gait retraining is advisable. Consider using a knee brace for support.' if sym < 0.85 else 'Continue regular monitoring. Strengthening exercises will help maintain symmetry.'}"""


def _general_response(risk, level):
    return f"""## OA Detection System — Clinical Summary

Current overall OA risk level: **{level} ({risk:.1%})**

This AI-assisted screening system monitors 12 biomarkers across 4 sensor modalities:
1. **Acoustic** — joint crepitus frequency and amplitude
2. **Thermal** — synovial inflammation via IR temperature
3. **Kinematic** — range of motion and gait symmetry via IMU
4. **Mechanical** — flexion angle and stiffness via flex sensor

You can ask me about:
- "What does my risk score mean?"
- "Explain the crepitus reading"
- "What diet should I follow?"
- "Suggest exercises for my condition"
- "What does the temperature reading indicate?"

*Always consult an orthopedic specialist for clinical decisions.*"""


def _diet_summary(risk, level):
    return generate_diet_plan({"risk_score": risk, "risk_level": level})["summary"]


def _exercise_summary(risk, rom):
    protocol = generate_exercise_protocol(risk, rom, 0.85)
    lines = [f"## Recommended Exercise Protocol\n"]
    for ex in protocol[:3]:
        lines.append(f"**{ex['name']}** — {ex['duration']} | {ex['reps']}")
        lines.append(f"_{ex['rationale']}_\n")
    return "\n".join(lines)


# ─── DIET PLAN ────────────────────────────────────────────────────────────────

def generate_diet_plan(patient_data: dict) -> dict:
    """Generate a structured anti-inflammatory diet plan based on OA risk."""
    risk   = patient_data.get("risk_score", 0)
    level  = patient_data.get("risk_level", "LOW")
    bmi    = patient_data.get("bmi", 25)
    age    = patient_data.get("age", 50)

    model = _get_model()
    if model:
        try:
            prompt = f"""Generate a structured anti-inflammatory diet plan for an OA patient with:
- OA Risk Score: {risk:.1%} ({level})
- BMI: {bmi}, Age: {age}
- Context: Northeast India, should include locally available foods

Provide:
1. A brief summary (2-3 sentences)
2. Top 5 beneficial foods with reasons
3. Top 5 foods to avoid with reasons  
4. A 7-day meal plan (breakfast, lunch, dinner, snack) in a compact format
5. Daily calorie target estimate

Format as JSON with keys: summary, beneficial_foods, avoid_foods, meal_plan (list of 7 dicts), calorie_target"""
            response = model.generate_content(prompt)
            text = response.text
            # Try to parse JSON from response
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            print(f"[LLM] Diet plan Gemini error: {e}")

    # Rule-based diet plan
    return _rule_based_diet(risk, level, bmi)


def _rule_based_diet(risk, level, bmi):
    calorie_target = max(1400, 2200 - int(bmi - 22) * 30) if bmi else 1800

    beneficial_foods = [
        {"food": "Turmeric (Haldi)", "reason": "Curcumin reduces joint inflammation (IL-6, TNF-α inhibitor)", "quantity": "1 tsp/day in warm milk or curries"},
        {"food": "Fatty fish (Rohu, Katla, Salmon)", "reason": "Omega-3 fatty acids (EPA/DHA) reduce synovial inflammation", "quantity": "2–3 servings/week"},
        {"food": "Ginger (Adrak)", "reason": "Gingerols inhibit prostaglandin synthesis; reduces pain", "quantity": "2–3 cm piece/day in tea"},
        {"food": "Green leafy vegetables (Spinach, Sarson)", "reason": "Vitamin K supports cartilage health; antioxidants reduce oxidative damage", "quantity": "1–2 cups/day"},
        {"food": "Walnuts & Flaxseeds (Akhrot, Alsi)", "reason": "Plant-based Omega-3; reduces inflammatory markers", "quantity": "Handful/day"},
        {"food": "Amla (Indian Gooseberry)", "reason": "Highest natural Vitamin C; essential for collagen synthesis in cartilage", "quantity": "1–2 fresh or 1 tsp powder/day"},
        {"food": "Low-fat dairy (Dahi, Paneer)", "reason": "Calcium + Vitamin D for bone density; prevents subchondral bone loss", "quantity": "2 servings/day"},
    ]

    avoid_foods = [
        {"food": "Processed/packaged snacks", "reason": "Trans fats trigger inflammatory cytokines; accelerate cartilage breakdown"},
        {"food": "White sugar & sweets (mithai)", "reason": "High AGEs (Advanced Glycation Endproducts) damage collagen in cartilage"},
        {"food": "Red meat (especially red meat curries)", "reason": "Arachidonic acid → pro-inflammatory eicosanoids"},
        {"food": "Refined carbs (Maida, white rice excess)", "reason": "Promotes insulin resistance; associated with higher OA pain scores"},
        {"food": "Excessive salt & pickle (Achar)", "reason": "Promotes fluid retention; increases joint swelling"},
    ]

    meal_plan = [
        {"day": "Mon", "breakfast": "Oatmeal porridge with walnuts + Amla juice", "lunch": "Brown rice + dal palak + cucumber raita", "dinner": "Rohu fish curry + 1 roti + sautéed vegetables", "snack": "Turmeric milk + handful of almonds"},
        {"day": "Tue", "breakfast": "Moong dal chilla + ginger-lemon tea", "lunch": "Mixed vegetable khichdi + low-fat curd", "dinner": "Grilled paneer tikka + dal tadka + brown rice", "snack": "Flaxseed chutney with whole wheat crackers"},
        {"day": "Wed", "breakfast": "Boiled egg + multigrain toast + green tea", "lunch": "Rajma (kidney beans) + brown rice + salad", "dinner": "Steamed fish + palak (spinach) soup + 1 roti", "snack": "Amla murabba + walnuts"},
        {"day": "Thu", "breakfast": "Dalia (broken wheat) upma + Amla juice", "lunch": "Chana dal + lauki sabzi + 2 rotis", "dinner": "Chicken curry (skinless) + mixed veg + brown rice", "snack": "Turmeric golden milk"},
        {"day": "Fri", "breakfast": "Idli (steamed) + sambar (light) + coconut chutney", "lunch": "Soya chunks curry + brown rice + salad", "dinner": "Baked fish + methi (fenugreek) roti + dal", "snack": "Roasted flaxseeds + fruits"},
        {"day": "Sat", "breakfast": "Sprouted moong salad + ginger tea", "lunch": "Matar paneer (low oil) + brown rice + raita", "dinner": "Lentil soup + 2 multigrain rotis + stir-fried vegetables", "snack": "Dry fruits mix (no cashews)"},
        {"day": "Sun", "breakfast": "Poha with peas + lime + Amla juice", "lunch": "Mixed dal + bottle gourd sabzi + rice", "dinner": "Grilled chicken / fish + roasted vegetables + 1 roti", "snack": "Turmeric milk + handful of walnuts"},
    ]

    summary = (
        f"For {'HIGH' if risk >= 0.55 else 'MEDIUM' if risk >= 0.35 else 'LOW'} OA risk, "
        f"an anti-inflammatory diet rich in Omega-3 fatty acids, curcumin, and Vitamin C is recommended. "
        f"Focus on whole grains, fatty fish, turmeric, and ginger. Avoid processed foods, excess sugar, and red meat. "
        f"Estimated daily calorie target: {calorie_target} kcal (adjusted for BMI {bmi})."
    )

    return {
        "summary": summary,
        "beneficial_foods": beneficial_foods,
        "avoid_foods": avoid_foods,
        "meal_plan": meal_plan,
        "calorie_target": calorie_target,
        "hydration_tip": "Drink 8–10 glasses of water/day. Adequate hydration maintains synovial fluid viscosity.",
        "supplement_note": "Consider Glucosamine (500mg) + Chondroitin (400mg) supplementation after medical advice. Vitamin D3 + K2 supplementation if deficient.",
    }


# ─── EXERCISE PROTOCOL ────────────────────────────────────────────────────────

def generate_exercise_protocol(risk_score: float, rom_deg: float, gait_symmetry: float) -> list:
    """
    Generate a personalized rehab exercise protocol based on OA severity.
    Returns a list of exercise card dicts.
    """
    model = _get_model()
    if model:
        try:
            prompt = f"""Generate a safe, evidence-based knee OA rehabilitation exercise protocol for:
- OA Risk Score: {risk_score:.1%}
- Knee Flexion ROM: {rom_deg:.0f}°
- Gait Symmetry: {gait_symmetry:.2f}

Return JSON array of 6 exercises, each with:
- name, type (strengthening/flexibility/aerobic/balance), difficulty (Low/Medium/High),
- duration, reps, sets, instructions (2-3 sentences), rationale (1 sentence), emoji, precautions"""
            response = model.generate_content(prompt)
            text = response.text
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            print(f"[LLM] Exercise protocol Gemini error: {e}")

    return _rule_based_exercises(risk_score, rom_deg)


def _rule_based_exercises(risk_score, rom_deg):
    high_risk = risk_score >= 0.55
    low_rom   = rom_deg < 80

    exercises = []

    # Always include: Quadriceps set (isometric — safe for all levels)
    exercises.append({
        "name": "Quadriceps Set (Isometric)",
        "type": "strengthening",
        "difficulty": "Low",
        "emoji": "💪",
        "duration": "10 minutes",
        "reps": "10–15 reps",
        "sets": "3 sets",
        "instructions": "Sit or lie flat with legs extended. Tighten the thigh muscle of the affected leg and press the back of the knee down. Hold for 5 seconds, then relax.",
        "rationale": "Strengthens quadriceps without joint loading — essential for OA management.",
        "precautions": "Stop if sharp pain occurs. Do not hyperextend the knee.",
    })

    # Straight Leg Raise
    exercises.append({
        "name": "Straight Leg Raise",
        "type": "strengthening",
        "difficulty": "Low",
        "emoji": "🦵",
        "duration": "8 minutes",
        "reps": "10 reps",
        "sets": "3 sets",
        "instructions": "Lie flat. Bend the healthy knee, keep affected leg straight. Tighten thigh muscles and raise the straight leg to 45°. Hold 3 seconds, slowly lower.",
        "rationale": "Builds hip flexor and quadriceps strength to reduce knee joint load during walking.",
        "precautions": "Avoid if you have lower back pain. Perform slowly and controlled.",
    })

    if not high_risk:
        # Heel slides — ROM exercise
        exercises.append({
            "name": "Heel Slides",
            "type": "flexibility",
            "difficulty": "Low",
            "emoji": "🛋️",
            "duration": "10 minutes",
            "reps": "15 reps",
            "sets": "2 sets",
            "instructions": "Lie on your back. Slowly slide your heel toward your buttocks, bending your knee as far as comfortable. Hold 5 seconds and slowly return.",
            "rationale": "Gently improves knee flexion ROM — reduces stiffness without compressive loading.",
            "precautions": "Do not force past comfortable ROM. Should feel a gentle stretch, not pain.",
        })

    # Step-ups (if ROM is reasonable)
    if not low_rom and not high_risk:
        exercises.append({
            "name": "Mini Step-Ups",
            "type": "strengthening",
            "difficulty": "Medium",
            "emoji": "🪜",
            "duration": "10 minutes",
            "reps": "10 reps per leg",
            "sets": "2 sets",
            "instructions": "Use a 10–15 cm step. Step up leading with the affected leg, bring other foot up. Step down with healthy leg first. Use a railing for balance.",
            "rationale": "Functional weight-bearing exercise that improves knee stability and muscle endurance.",
            "precautions": "Use handrail. Avoid if pain increases during weight-bearing.",
        })

    # Aqua therapy (aerobic — always recommend)
    exercises.append({
        "name": "Water Walking / Pool Therapy",
        "type": "aerobic",
        "difficulty": "Low",
        "emoji": "🏊",
        "duration": "20–30 minutes",
        "reps": "Continuous",
        "sets": "1 session",
        "instructions": "Walk in a swimming pool at waist height. Water buoyancy reduces joint load by ~50%. Walk forward, backward, and sideways.",
        "rationale": "Best aerobic exercise for OA — full cardiovascular benefit with minimal joint stress.",
        "precautions": "Ensure pool is at comfortable temperature (32–34°C). Use pool shoes for grip.",
    })

    # Chair yoga / seated stretches
    exercises.append({
        "name": "Seated Calf Raises",
        "type": "strengthening",
        "difficulty": "Low",
        "emoji": "🧘",
        "duration": "5 minutes",
        "reps": "20 reps",
        "sets": "3 sets",
        "instructions": "Sit upright on a chair with feet flat on the floor. Slowly raise both heels as high as comfortable. Hold 2 seconds at the top, lower slowly.",
        "rationale": "Improves circulation in the lower limbs and strengthens calf and ankle stabilizers.",
        "precautions": "Sit in a stable chair with armrests. Keep movements slow and controlled.",
    })

    # Balance training (if gait issues)
    exercises.append({
        "name": "Single-Leg Balance (Supported)",
        "type": "balance",
        "difficulty": "Medium" if not high_risk else "Low",
        "emoji": "⚖️",
        "duration": "8 minutes",
        "reps": "10 seconds hold per leg",
        "sets": "5 reps per side",
        "instructions": "Stand near a wall or sturdy chair. Lift the healthy foot slightly and balance on the affected leg. Increase time as you improve.",
        "rationale": "Improves proprioception and joint stability — reduces risk of falls in OA patients.",
        "precautions": "Always stand near a support. Do not attempt if severe pain or instability is present.",
    })

    return exercises


# ─── CLINICAL SUMMARY ─────────────────────────────────────────────────────────

def get_clinical_summary(patient_id: str, patient_data: dict, latest_reading: dict, trend: dict) -> str:
    """Generate a concise clinical narrative summary for the PDF report."""
    risk  = latest_reading.get("risk_score", 0)
    level = latest_reading.get("risk_level", "UNKNOWN")
    rom   = latest_reading.get("flex_angle_deg", 0)
    crep  = latest_reading.get("crepitus_score", 0)
    temp  = latest_reading.get("joint_temp_c", 33)
    sym   = latest_reading.get("step_symmetry", 1.0)
    name  = patient_data.get("name", "Patient")
    age   = patient_data.get("age", "?")

    model = _get_model()
    if model:
        try:
            ctx = _format_context(patient_id, {
                "patient": patient_data,
                "latest_reading": latest_reading,
                "trend_summary": trend
            })
            prompt = f"{ctx}\n\nGenerate a 3-paragraph clinical narrative summary for a PDF report. Be concise, professional, and clinical. Include key findings, clinical interpretation, and recommendations."
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"[LLM] Summary Gemini error: {e}")

    # Fallback narrative
    trend_dir = trend.get("direction", "stable")
    return (
        f"{name} (Age: {age}) was assessed using the OA Detection System wearable platform. "
        f"The AI ensemble model assigned an overall OA risk score of {risk:.1%} ({level} risk). "
        f"Key sensor findings include: crepitus score {crep:.2f} (threshold >0.30 = abnormal), "
        f"joint temperature {temp:.1f}°C {'(elevated, suggesting synovial inflammation)' if temp > 34.5 else '(within normal range)'}, "
        f"knee flexion ROM {rom:.0f}° {'(reduced)' if rom < 90 else '(acceptable)'}, and "
        f"gait symmetry index {sym:.2f} {'(asymmetric)' if sym < 0.85 else '(normal)'}.\n\n"
        f"The 30-day trend analysis shows a {trend_dir} trajectory in OA risk markers. "
        f"{'Progression of OA indicators warrants prompt orthopedic referral.' if trend_dir == 'worsening' else 'Current management appears to be maintaining joint health.'}\n\n"
        f"{'RECOMMENDATION: Urgent orthopedic consultation recommended. X-ray (weight-bearing AP + lateral views) and KL grading assessment advised.' if risk >= 0.55 else 'RECOMMENDATION: Continue regular monitoring. Anti-inflammatory lifestyle measures (diet, low-impact exercise) and follow-up in 4 weeks.'}"
    )


def is_available() -> dict:
    return {
        "gemini_available": GEMINI_AVAILABLE and bool(GEMINI_API_KEY),
        "mode": "gemini" if (GEMINI_AVAILABLE and GEMINI_API_KEY) else "rule-based",
        "model": "gemini-1.5-flash" if (GEMINI_AVAILABLE and GEMINI_API_KEY) else "offline-rule-engine",
    }
