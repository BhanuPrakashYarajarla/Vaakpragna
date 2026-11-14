from flask import Blueprint, render_template, request, jsonify
import requests
from features.gemini_client import generate_text

# === Grammar API ===
LANGUAGETOOL_URL = "https://api.languagetool.org/v2/check"

# === Blueprint Setup ===
text_analyzer_bp = Blueprint("text_analyzer", __name__)

# === Gemini Prompt Function ===
def get_gemini_feedback(text):
    prompt = f"""
You are a grammar assistant. For the text below, reply **strictly in this format**:

Suggestions:
Grammar: [brief explanation]
Style & Clarity: [brief explanation]

Corrected Sentence: [only the revised sentence]

Tone: [one-sentence tone description]

⚠️ Do NOT repeat or restate the original input.
⚠️ Do NOT include extra commentary.
⚠️ Do NOT add headings like "Tone Assessment" — only what's asked.

Text:
{text}
"""
    try:
        return generate_text(prompt).strip()
    except Exception as e:
        return f"⚠️ Gemini API error: {str(e)}"

# === Routes ===

@text_analyzer_bp.route("/text-analyzer", methods=["GET"])
def text_analyzer_page():
    return render_template("text-analyzer.html")

@text_analyzer_bp.route("/check_grammar", methods=["POST"])
def check_grammar_route():
    text = request.json.get("text", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400

    # Run LanguageTool check
    params = {"text": text, "language": "en-US"}
    response = requests.post(
        LANGUAGETOOL_URL,
        data=params,
        timeout=20
    )
    response.raise_for_status()
    data = response.json()

    corrections = []
    corrected_text = text
    offset_correction = 0

    for match in data.get("matches", []):
        if match["replacements"]:
            replacement = match["replacements"][0]["value"]
            start = match["offset"] + offset_correction
            end = start + match["length"]
            corrected_text = corrected_text[:start] + replacement + corrected_text[end:]
            offset_correction += len(replacement) - match["length"]

            corrections.append({
                "message": match["message"],
                "replacement": replacement,
                "context": match["context"]["text"]
            })

    # Basic Grammar Judgment
    num_mistakes = len(corrections)
    if num_mistakes == 0:
        judgment = "✅ Excellent! No mistakes detected."
    elif num_mistakes <= 2:
        judgment = "⚠️ Minor issues. Nearly perfect."
    else:
        judgment = "❌ Needs Improvement! Several grammar mistakes found."

    # Gemini feedback
    gemini_feedback = get_gemini_feedback(text)

    return jsonify({
        "text": text,
        "corrections": corrections,
        "judgment": judgment,
        "corrected_text": corrected_text,
        "gemini_feedback": gemini_feedback
    })
