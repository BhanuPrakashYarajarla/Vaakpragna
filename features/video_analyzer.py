# Set environment variables before any imports to suppress TensorFlow warnings
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['GLOG_minloglevel'] = '3'

import logging
logging.getLogger('tensorflow').setLevel(logging.ERROR)
logging.getLogger('absl').setLevel(logging.ERROR)
logging.getLogger('mediapipe').setLevel(logging.ERROR)

from flask import Blueprint, render_template, request, jsonify
import cv2, re, base64, time
import numpy as np
from features.gemini_client import generate_text

logger = logging.getLogger(__name__)

video_analyzer_bp = Blueprint("video_analyzer", __name__)

# === MediaPipe Face Mesh & Pose with OpenCV fallback ===
try:
    import mediapipe as mp
    mp_face_mesh = getattr(mp.solutions, 'face_mesh', None) if hasattr(mp, 'solutions') else None
    mp_pose = getattr(mp.solutions, 'pose', None) if hasattr(mp, 'solutions') else None
except Exception:
    mp = None
    mp_face_mesh = None
    mp_pose = None

# Built-in OpenCV cascades for resilient fallback
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')

# === Per-session analysis state ===
_analysis_sessions = {}
_SESSION_TIMEOUT = 300  # 5 minutes
_GEMINI_INTERVAL = 12   # seconds between Gemini calls

# Max frame payload size (2 MB base64 ≈ ~1.5 MB image)
_MAX_FRAME_SIZE = 2 * 1024 * 1024


def _get_session(session_id):
    """Get or create an analysis session, cleaning up expired ones."""
    now = time.time()
    expired = [k for k, v in _analysis_sessions.items()
               if now - v['last_active'] > _SESSION_TIMEOUT]
    for k in expired:
        del _analysis_sessions[k]

    if session_id not in _analysis_sessions:
        _analysis_sessions[session_id] = {
            'frame_count': 0,
            'face_count': 0,
            'pose_count': 0,
            'eye_contact_count': 0,
            'last_gemini_call': 0,
            'last_active': now,
            'latest_feedback': {
                'judgment': '',
                'eye_contact': '',
                'body_language': '',
                'tone_pace': '',
                'tips': ''
            }
        }
    else:
        _analysis_sessions[session_id]['last_active'] = now
    return _analysis_sessions[session_id]


# === Routes ===

@video_analyzer_bp.route("/video-analyzer")
def video_page():
    return render_template("video-analyzer.html")


@video_analyzer_bp.route("/analyze_frame", methods=["POST"])
def analyze_frame():
    """Receive a base64 JPEG frame from the browser, run local CV analysis,
    and periodically aggregate stats for a Gemini feedback call."""
    data = request.get_json()
    if not data or 'frame' not in data:
        return jsonify({'error': 'No frame data provided'}), 400

    session_id = data.get('session_id', 'default')
    frame_b64 = data['frame']

    # --- Input validation ---
    if len(frame_b64) > _MAX_FRAME_SIZE:
        return jsonify({'error': 'Frame too large (max 2 MB)'}), 400

    # Strip data-URL prefix if present
    if ',' in frame_b64:
        frame_b64 = frame_b64.split(',', 1)[1]

    try:
        frame_bytes = base64.b64decode(frame_b64)
    except Exception:
        return jsonify({'error': 'Invalid base64 data'}), 400

    # Validate JPEG magic bytes
    if not frame_bytes[:2] == b'\xff\xd8':
        return jsonify({'error': 'Invalid JPEG format'}), 400

    # Decode to numpy array
    nparr = np.frombuffer(frame_bytes, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify({'error': 'Could not decode image'}), 400

    h, w = frame.shape[:2]
    if h < 50 or w < 50 or h > 2160 or w > 3840:
        return jsonify({'error': f'Invalid frame dimensions: {w}x{h}'}), 400

    # --- Local CV processing ---
    session = _get_session(session_id)
    session['frame_count'] += 1

    face_detected = False
    eye_contact = False
    gaze_direction = "Center"
    pose_detected = False

    # 1. Face & Eye Contact Analysis with MediaPipe Face Mesh
    if mp_face_mesh:
        try:
            with mp_face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5
            ) as face_mesh:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = face_mesh.process(rgb)
                if results.multi_face_landmarks:
                    face_detected = True
                    session['face_count'] += 1
                    landmarks = results.multi_face_landmarks[0].landmark

                    # Left eye EAR: |y159 - y145| / |x133 - x33|
                    left_ear = abs(landmarks[159].y - landmarks[145].y) / (abs(landmarks[133].x - landmarks[33].x) + 1e-6)
                    # Right eye EAR: |y386 - y374| / |x263 - x362|
                    right_ear = abs(landmarks[386].y - landmarks[374].y) / (abs(landmarks[263].x - landmarks[362].x) + 1e-6)

                    eyes_open = (left_ear > 0.15 and right_ear > 0.15)

                    # Face yaw: nose tip (landmark 1) relative to cheek boundaries (234 & 454)
                    nose_x = landmarks[1].x
                    left_x = landmarks[234].x
                    right_x = landmarks[454].x
                    face_w = abs(right_x - left_x) + 1e-6
                    rel_nose_x = (nose_x - min(left_x, right_x)) / face_w

                    # Direct eye contact if eyes open and face is forward-facing
                    if eyes_open and 0.35 <= rel_nose_x <= 0.65:
                        eye_contact = True
                        session['eye_contact_count'] += 1
                        gaze_direction = "Direct Eye Contact"
                    elif rel_nose_x < 0.35:
                        gaze_direction = "Looking Right"
                    elif rel_nose_x > 0.65:
                        gaze_direction = "Looking Left"
                    elif not eyes_open:
                        gaze_direction = "Blinking / Eyes Closed"
                    else:
                        gaze_direction = "Averted"
        except Exception as e:
            logger.debug(f"MediaPipe FaceMesh note: {e}")

    # Fallback to OpenCV Haar Cascades if FaceMesh not available or no face found
    if not face_detected:
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60))
            if len(faces) > 0:
                face_detected = True
                session['face_count'] += 1
                (fx, fy, fw, fh) = faces[0]
                roi_gray = gray[fy:fy + int(fh * 0.6), fx:fx + fw]
                eyes = eye_cascade.detectMultiScale(roi_gray, scaleFactor=1.1, minNeighbors=4, minSize=(20, 20))
                if len(eyes) >= 1:
                    eye_contact = True
                    session['eye_contact_count'] += 1
                    gaze_direction = "Direct Eye Contact"
                else:
                    gaze_direction = "Averted"
        except Exception as e:
            logger.error(f"OpenCV face detection error: {e}")

    # 2. Pose detection with MediaPipe Pose
    if mp_pose:
        try:
            with mp_pose.Pose(
                static_image_mode=True,
                min_detection_confidence=0.5,
                model_complexity=0
            ) as pose:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = pose.process(rgb)
                if results.pose_landmarks:
                    pose_detected = True
                    session['pose_count'] += 1
        except Exception as e:
            logger.debug(f"Pose detection note: {e}")
    elif face_detected:
        # Graceful posture detection when pose solution is unavailable
        pose_detected = True
        session['pose_count'] += 1

    # Privacy: don't retain the frame after processing
    del frame, nparr, frame_bytes

    # --- Build local stats ---
    fc = session['frame_count']
    local_stats = {
        'face_detected': face_detected,
        'pose_detected': pose_detected,
        'eye_contact': eye_contact,
        'gaze_direction': gaze_direction,
        'eye_contact_ratio': f"{session['eye_contact_count']}/{fc}",
        'face_ratio': f"{session['face_count']}/{fc}",
        'pose_ratio': f"{session['pose_count']}/{fc}",
        'frames_analyzed': fc
    }

    # --- Periodic Gemini call (every ~12 s) ---
    now = time.time()
    feedback = session['latest_feedback']
    gemini_updated = False

    if now - session['last_gemini_call'] >= _GEMINI_INTERVAL and fc > 0:
        session['last_gemini_call'] = now

        eye_summary = (
            f"Face visible in {session['face_count']}/{fc} frames, "
            f"direct eye contact maintained in {session['eye_contact_count']}/{fc} frames. "
            f"Latest gaze: {gaze_direction}."
        )
        pose_summary = f"Speaker posture detected in {session['pose_count']}/{fc} frames."

        try:
            prompt = build_student_prompt(eye_summary, pose_summary, "Live session")
            result = call_gemini(prompt)
            feedback.update({
                'judgment': result.get('judgment', 'Not available'),
                'eye_contact': result.get('eye_contact', 'Not available'),
                'body_language': result.get('body_language', 'Not available'),
                'tips': result.get('tips', 'Not available')
            })
            gemini_updated = True
        except Exception as e:
            logger.error(f"Gemini feedback error: {e}")

        # Reset counters for the next aggregation window
        session['face_count'] = 0
        session['pose_count'] = 0
        session['eye_contact_count'] = 0
        session['frame_count'] = 0

    return jsonify({
        'stats': local_stats,
        'feedback': feedback,
        'gemini_updated': gemini_updated
    })


@video_analyzer_bp.route("/reset_session", methods=["POST"])
def reset_session():
    """Clean up analysis session when the user stops."""
    data = request.get_json() or {}
    session_id = data.get('session_id', 'default')
    if session_id in _analysis_sessions:
        del _analysis_sessions[session_id]
    return jsonify({'message': 'Session reset'})


@video_analyzer_bp.route("/live_feedback")
def live_feedback():
    session_id = request.args.get('session_id', 'default')
    session = _get_session(session_id)
    return jsonify(session['latest_feedback'])


@video_analyzer_bp.route("/analyze_voice", methods=["POST"])
def analyze_voice():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    transcript = data.get("transcript", "")
    speech_rate = data.get("speech_rate", 0)
    pitch_variation = data.get("pitch_variation", 0)

    if not transcript:
        return jsonify({"error": "No transcript provided"}), 400

    voice_info = f"Speech rate: {speech_rate} words/min, Pitch variation: {pitch_variation}"
    prompt = build_voice_prompt(voice_info)
    result = call_gemini(prompt)
    if "error" in result:
        return jsonify(result), 500

    session_id = data.get('session_id', 'default')
    session = _get_session(session_id)
    session['latest_feedback']['tone_pace'] = result.get("tone_pace", "Not available")
    return jsonify(session['latest_feedback'])


# === Prompt builders and Gemini helpers ===

def build_student_prompt(eye_info, pose_info, topic_summary):
    return f"""
You are a professional public speaking coach providing concise, actionable feedback.
Analyze the following and respond with feedback in the format below (1 sentence each):
1. Overall Judgment: [Your judgment here]
2. Eye Contact Feedback: [Your feedback here]
3. Body Language Feedback: [Your feedback here]
4. Improvement Tips: [Your tips here]
Use a positive, encouraging tone.

## Eye Tracking:
{eye_info}

## Body Language:
{pose_info}

## Topic:
{topic_summary}
"""


def build_voice_prompt(voice_info):
    return f"""
You are a professional public speaking coach.

Given the voice metrics below, identify the speaker's **tone** (e.g., formal, casual, nervous, enthusiastic, monotone, robotic, dynamic, persuasive) and provide clear, encouraging feedback on how the tone and pace affect delivery. Suggest specific improvements if needed.

Respond exactly in this format:
1. Detected Tone: [one phrase only]
2. Tone and Pace Feedback: [one brief sentence giving advice or praise]

Voice Metrics:
{voice_info}
"""


def call_gemini(prompt):
    try:
        full_text = generate_text(prompt).strip()

        if "Voice Metrics" in prompt:
            tone_detected = extract_section(full_text, "1. Detected Tone:")
            tone_feedback = extract_section(full_text, "2. Tone and Pace Feedback:")
            return {
                "tone_pace": f"{tone_feedback} (Tone detected: {tone_detected})"
                             if tone_feedback and tone_detected else "Not available"
            }

        return {
            "judgment": extract_section(full_text, "1. Overall Judgment:"),
            "eye_contact": extract_section(full_text, "2. Eye Contact Feedback:"),
            "body_language": extract_section(full_text, "3. Body Language Feedback:"),
            "tips": extract_section(full_text, "4. Improvement Tips:")
        }
    except Exception as e:
        logger.error(f"Gemini API error: {str(e)}")
        if "Voice Metrics" in prompt:
            return {"tone_pace": "Error in analysis"}
        return {
            "judgment": "Error in analysis",
            "eye_contact": "Error in analysis",
            "body_language": "Error in analysis",
            "tips": "Error in analysis"
        }


def extract_section(text, marker):
    pattern = rf"{re.escape(marker)}\s*(.*?)(?=\n\d+\.|\Z|-|\n\n)"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip().lstrip("*\u2022- ").strip()
    if marker in text:
        parts = text.split(marker, 1)
        if len(parts) > 1:
            next_section = parts[1].split('\n', 1)[0].strip()
            return next_section.lstrip("*\u2022- ").strip()
    return "Not available"
