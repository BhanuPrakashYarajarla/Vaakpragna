from flask import Blueprint, request, jsonify, render_template
import random
import time
import uuid
import logging
import re
from features.gemini_client import generate_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

debate_bp = Blueprint('debate', __name__, template_folder='../templates', static_folder='../static')

debate_topics = [
    "AI in Education",
    "Climate Change Policies",
    "Universal Basic Income",
    "Social Media Regulation",
    "Space Exploration Funding",
    "Genetic Engineering Ethics",
    "Renewable Energy Adoption",
    "Privacy vs. Security",
    "Legalization of Recreational Marijuana",
    "Automation and Job Displacement"
]


# === Per-room AI debate state ===
_debate_rooms = {}
_ROOM_TIMEOUT = 3600  # 1 hour


def _cleanup_rooms():
    """Remove expired rooms."""
    now = time.time()
    expired = [k for k, v in _debate_rooms.items()
               if now - v['last_active'] > _ROOM_TIMEOUT]
    for k in expired:
        del _debate_rooms[k]


def _get_room(room_id):
    """Get an existing room. Returns None if not found or expired."""
    _cleanup_rooms()
    room = _debate_rooms.get(room_id)
    if room:
        room['last_active'] = time.time()
    return room


def _create_room():
    """Create a new debate room. Returns (room_id, room_state)."""
    _cleanup_rooms()
    room_id = str(uuid.uuid4())[:8]
    now = time.time()
    _debate_rooms[room_id] = {
        'current_topic': None,
        'debate_style': 'Formal',
        'ai_difficulty': 'Intermediate',
        'time_per_turn': 30,
        'num_rounds': 3,
        'current_round': 1,
        'dialogues': [],
        'user_score': 0,
        'ai_score': 0,
        'last_active': now,
        'created_at': now
    }
    return room_id, _debate_rooms[room_id]


# === AI Debate Routes ===

@debate_bp.route('/')
def index():
    return render_template('debate-with-ai.html')


@debate_bp.route('/roll_dice', methods=['POST'])
def roll_dice():
    topic = random.choice(debate_topics)
    return jsonify({'topic': topic})


@debate_bp.route('/accept_topic', methods=['POST'])
def accept_topic():
    data = request.json
    if not data or not data.get('topic'):
        return jsonify({'error': 'Topic is required'}), 400

    num_rounds = str(data.get('num_rounds', '')).strip()
    if not num_rounds or not num_rounds.isdigit() or int(num_rounds) < 1:
        return jsonify({'error': 'Please enter a valid number of rounds (at least 1).'}), 400

    room_id, room = _create_room()
    room['current_topic'] = data['topic']
    room['num_rounds'] = int(num_rounds)
    room['current_round'] = 1

    return jsonify({
        'status': 'success',
        'room_id': room_id,
        'round': room['current_round']
    })


@debate_bp.route('/set_debate_settings', methods=['POST'])
def set_debate_settings():
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    room_id = data.get('room_id')
    room = _get_room(room_id) if room_id else None

    if not room:
        # Settings sent before accept_topic — create a temporary room
        room_id, room = _create_room()

    room['debate_style'] = data.get('style', room['debate_style'])
    room['ai_difficulty'] = data.get('difficulty', room['ai_difficulty'])
    room['time_per_turn'] = int(data.get('time_per_turn', room['time_per_turn']))

    return jsonify({'status': 'success', 'room_id': room_id})


@debate_bp.route('/generate_ai_response', methods=['POST'])
def generate_ai_response():
    try:
        data = request.json
        if not data or not data.get('user_input'):
            return jsonify({'error': 'No input provided'}), 400

        room_id = data.get('room_id')
        room = _get_room(room_id) if room_id else None

        if not room:
            return jsonify({
                'error': 'Invalid or expired debate session. Please start a new debate.'
            }), 400

        user_input = data['user_input']

        # Validate input length
        if len(user_input) > 5000:
            return jsonify({'error': 'Input too long (max 5000 characters)'}), 400

        room['dialogues'].append({
            'speaker': 'You',
            'text': user_input,
            'time': time.strftime('%H:%M')
        })

        # Professional debate prompt
        prompt = f"""Act as a professional debate opponent on the topic: {room['current_topic']}.
        The debate style is {room['debate_style']}.
        My last argument was: \"{user_input}\"
        
        Respond concisely in 2-3 lines maximum, following these rules:
        1. Acknowledge my point briefly
        2. Present a clear counter-argument
        3. Use professional but engaging language
        4. Maintain logical consistency
        5. Keep response under 40 words if possible
        6. Make sure to use the same language as the user.
        7. Make sure to use the same tone as the user.
        8. Stay close to the topic, don't get carried away.
        
        Example formats:
        - \"While I understand your point about X, the evidence suggests Y because Z.\"
        - \"That's an interesting perspective, but have you considered X? Studies show Y.\"
        - \"I respectfully disagree because X. The data indicates Y which contradicts your point.\"
        """

        response_text = generate_text(
            prompt, max_output_tokens=50, temperature=0.7
        ).strip()

        # Detect complex words
        complex_words = detect_complex_words(response_text)
        complex_word_data = []
        for word in complex_words:
            definition = get_word_definition(word)
            if definition:
                complex_word_data.append({
                    'word': word,
                    'definition': definition
                })

        # Ensure response is concise
        if len(response_text.split()) > 30:
            sentences = response_text.split('. ')
            response_text = ('. '.join(sentences[:2]) + '.'
                             if len(sentences) > 1 else sentences[0])

        room['dialogues'].append({
            'speaker': 'AI Opponent',
            'text': response_text,
            'time': time.strftime('%H:%M')
        })

        # Check if round is complete (10 exchanges = 5 from each side)
        user_exchanges = len([d for d in room['dialogues']
                              if d['speaker'] == 'You'])
        ai_exchanges = len([d for d in room['dialogues']
                            if d['speaker'] == 'AI Opponent'])
        round_complete = (user_exchanges + ai_exchanges) >= 10
        end = False
        analysis = None

        if round_complete:
            analysis = analyze_debate(room)
            # Handle nonsense-argument edge case
            if (isinstance(analysis.get('strengths'), str)
                    and "Unintended Humor" in analysis['strengths']):
                analysis['strengths'] = ("1. Efficient communication\n"
                                         "2. Engaged audience emotionally")
                analysis['weaknesses'] = ("1. Lacked substantive arguments\n"
                                          "2. Failed to address the topic\n"
                                          "3. No engagement with opponent")
                analysis['improvements'] = ("1. Research the topic thoroughly\n"
                                            "2. Develop a clear stance\n"
                                            "3. Support arguments with evidence")
            room['current_round'] += 1
            room['dialogues'] = []
            if room['current_round'] > room['num_rounds']:
                end = True
                # Clean up finished debate
                _debate_rooms.pop(room_id, None)
            return jsonify({
                'response': response_text,
                'complex_words': complex_word_data,
                'round': room['current_round'] - 1,
                'analysis': analysis,
                'end': end
            })

        return jsonify({
            'response': response_text,
            'complex_words': complex_word_data,
            'round': room['current_round']
        })

    except Exception as e:
        logger.error(f"Error in generate_ai_response: {str(e)}")
        return jsonify({
            'error': f'Failed to generate AI response: {str(e)}'
        }), 500


# === Friend-vs-Friend Stateless Judgement ===

@debate_bp.route('/judge_friend_debate', methods=['POST'])
def judge_friend_debate():
    """Stateless endpoint: receives arguments from both players, returns
    an AI judgement.  No room state is created or required."""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        topic = data.get('topic', 'General Debate')
        player1_args = data.get('player1_arguments', [])
        player2_args = data.get('player2_arguments', [])

        if not player1_args and not player2_args:
            return jsonify({'error': 'No arguments provided'}), 400

        # Accept a list of strings or a single string
        if isinstance(player1_args, str):
            player1_text = player1_args
        else:
            player1_text = '\n'.join(str(a) for a in player1_args)

        if isinstance(player2_args, str):
            player2_text = player2_args
        else:
            player2_text = '\n'.join(str(a) for a in player2_args)

        # Validate input lengths
        if len(player1_text) > 10000 or len(player2_text) > 10000:
            return jsonify({
                'error': 'Arguments too long (max 10 000 characters each)'
            }), 400

        prompt = f"""
You are a professional debate judge.

Analyze the arguments of two players on the topic: "{topic}".
Structure your response like this:

🏆 Winner: Player X

🎯 Player 1
Score: (number out of 100)
Strengths:
- ...
Weaknesses:
- ...
Improvements:
- ...

🎯 Player 2
Score: (number out of 100)
Strengths:
- ...
Weaknesses:
- ...
Improvements:
- ...

Be detailed and fair. No extra commentary.

Player 1: {player1_text}
Player 2: {player2_text}
"""

        result_text = generate_text(
            prompt, max_output_tokens=500, temperature=0.3
        ).strip()

        # Extract winner
        winner_match = re.search(r'🏆 Winner: (Player \d)', result_text)
        winner = winner_match.group(1) if winner_match else "Draw"

        return jsonify({
            'judgement': result_text,
            'winner': winner
        })

    except Exception as e:
        logger.error(f"Error in judge_friend_debate: {str(e)}")
        return jsonify({
            'error': f'Failed to generate judgement: {str(e)}',
            'judgement': 'An error occurred while generating the judgement. '
                         'Please try again.',
            'winner': 'Draw'
        }), 500


# === Internal helpers ===

def get_word_definition(word):
    try:
        prompt = (f'Provide a simple, one-sentence definition for the word '
                  f'"{word}" that would be understandable by a high school '
                  f'student.\nReturn ONLY the definition with no additional '
                  f'text or formatting.')
        return generate_text(prompt).strip()
    except Exception as e:
        logger.error(f"Error getting definition for {word}: {str(e)}")
        return None


def analyze_debate(room):
    user_dialogues = [d['text'] for d in room['dialogues']
                      if d['speaker'] == 'You']
    ai_dialogues = [d['text'] for d in room['dialogues']
                    if d['speaker'] == 'AI Opponent']

    try:
        prompt = f"""Act as a professional debate judge analyzing this \
{room['debate_style']} debate on {room['current_topic']}.

        User Arguments:
        {user_dialogues}

        AI Opponent Arguments:
        {ai_dialogues}

        Provide a detailed analysis with these EXACT section headers:
        [Strengths]
        [Weaknesses]
        [Improvements]
        [Score]
        [Winner]

        For each section, provide 2-3 concise bullet points (except Score \
which should be a number 0-100 and Winner which should be either \
"User" or "AI Opponent").

        Example format:
        [Strengths]
        - Clear logical structure
        - Good use of evidence
        [Weaknesses]
        - Lacked counter-arguments
        - Needed more examples
        [Improvements]
        - Research more statistics
        - Address opponent's points directly
        [Score]
        75
        [Winner]
        AI Opponent
        """

        analysis_text = generate_text(
            prompt, max_output_tokens=400, temperature=0.3
        ).strip()

        # Defaults
        analysis = {
            'strengths': 'No strengths identified',
            'weaknesses': 'No weaknesses identified',
            'improvements': 'No suggestions provided',
            'score': 50,
            'winner': 'AI Opponent'
        }

        sections = re.split(r'\[(.*?)\]', analysis_text)
        for i in range(1, len(sections), 2):
            section_name = sections[i].strip()
            content = sections[i + 1].strip() if i + 1 < len(sections) else ""

            if section_name.lower() == 'strengths':
                analysis['strengths'] = content or 'No strengths identified'
            elif section_name.lower() == 'weaknesses':
                analysis['weaknesses'] = content or 'No weaknesses identified'
            elif section_name.lower() == 'improvements':
                analysis['improvements'] = content or 'No suggestions provided'
            elif section_name.lower() == 'score':
                try:
                    analysis['score'] = min(
                        100, max(0, int(re.search(r'\d+', content).group())))
                except Exception:
                    analysis['score'] = 50
            elif section_name.lower() == 'winner':
                if 'user' in content.lower():
                    analysis['winner'] = 'You'
                else:
                    analysis['winner'] = 'AI Opponent'

        for key in ['strengths', 'weaknesses', 'improvements']:
            analysis[key] = analysis[key].replace('- ', '\u2022 ').strip()
            if not analysis[key] or analysis[key] == 'No analysis available':
                analysis[key] = (f'No {key} identified'
                                 if key != 'improvements'
                                 else 'No suggestions provided')

        return analysis

    except Exception as e:
        logger.error(f"Error in analyze_debate: {str(e)}")
        return {
            'strengths': 'Analysis failed - please try again',
            'weaknesses': 'Analysis failed - please try again',
            'improvements': 'Analysis failed - please try again',
            'score': 50,
            'winner': 'AI Opponent'
        }


def detect_complex_words(text):
    try:
        prompt = (f'Analyze this text and identify any complex or difficult '
                  f'words that might be challenging for an average reader:'
                  f'\n\n"{text}"\n\nReturn ONLY a comma-separated list of '
                  f'the complex words you identify, with no additional '
                  f'explanation or formatting.\nIf no complex words are '
                  f'found, return an empty string.')
        result = generate_text(prompt).strip()
        complex_words = result.split(',') if result else []
        return [word.strip() for word in complex_words if word.strip()]
    except Exception as e:
        logger.error(f"Error detecting complex words: {str(e)}")
        return []
