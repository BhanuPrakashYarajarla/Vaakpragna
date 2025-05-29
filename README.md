# 🗣 Vaakpragna - AI Communication Companion

**Vaakpragna** is an AI-powered platform to help users improve their public speaking and debating skills through real-time analysis, intelligent feedback, and gamified tracking. It integrates text, voice, and facial gesture analysis for a complete communication evaluation experience.

---

## 🚀 Features

- 🎤 **Live Speech Analysis**  
  Real-time feedback on delivery using facial gestures, audio, and posture cues.
  
- 📝 **Text Analyzer**  
  Grammar checking, readability scoring, and structural feedback.

- 🧠 **Debate with AI**  
  Practice debating with an AI opponent that judges your arguments and delivery.

- 👁️ **Face Tracking**  
  Uses dlib and OpenCV to analyze eye contact, head movement, and attentiveness.

- 🗃️ **User Profiles**  
  Tracks individual progress, achievements, and personal stats using a local database.

- 🥇 **Gamification**  
  Earn badges and certificates by completing debate milestones.

---

## 📁 Project Structure

```
Vaakpragna/
│
├── features/
│   ├── __init__.py
│   ├── debate_with_ai.py
│   ├── shape_predictor_68_face_landmarks.dat
│   ├── text_analyzer.py
│   └── video_analyzer.py
│
├── static/
│   ├── images/
│   │   ├── dice.png
│   │   └── vaaklogo.jpg
│   ├── js/
│   │   ├── auth.js
│   │   ├── debate.js
│   │   └── video-analyzer.js
│   └── style.css
│
├── templates/
│   ├── create_new_room.html
│   ├── debate-with-ai.html
│   ├── friend_vs_friend.html
│   ├── index.html
│   ├── leaderboard.html
│   ├── login_signup.html
│   ├── profile.html
│   ├── text-analyzer.html
│   └── video-analyzer.html
│
├── main.py
├── requirements.txt
└── users.db
```

---

## ⚙️ Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/yourusername/Vaakpragna.git
   cd Vaakpragna
   ```

2. **Set Up Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the App**
   ```bash
   python main.py
   ```

---

## 🧠 Tech Stack

- **Backend**: Python, Flask, OpenCV, dlib, SQLite
- **Frontend**: HTML, Tailwind CSS, JavaScript
- **AI Integration**: Gemini API / OpenAI API for NLP feedback

---

## 🏅 Milestone System

| Badge         | Requirement            |
|---------------|------------------------|
| 🥉 Bronze      | Complete 25 debates    |
| 🥈 Silver      | Complete 50 debates    |
| 🥇 Gold + 🧾 Certificate | Complete 100+ debates |

---

## 📸 Profiles & Customization

- Users can customize profiles with avatars
- Progress is tracked via:
  - Number of debates
  - Badges earned
  - Certificate eligibility

---

## 👥 Contributors

-  **Sree Harshini** – UI/UX design and Frontend Development
-  **Bhanu Prakash** – AI & Backend Development 

