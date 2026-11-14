// Video Analyzer — browser camera capture + server-side CV analysis
document.addEventListener('DOMContentLoaded', function () {
    const startLiveBtn = document.getElementById('startLive');
    const stopLiveBtn  = document.getElementById('stopLive');
    const videoFeed    = document.getElementById('videoFeed');
    const recordingStatus = document.getElementById('recordingStatus');
    const judgmentEl     = document.getElementById('judgment');
    const eyeContactEl   = document.getElementById('eyeContact');
    const bodyLanguageEl = document.getElementById('bodyLanguage');
    const tonePaceEl     = document.getElementById('tonePace');
    const tipsEl         = document.getElementById('tips');

    let analysisInterval = null;
    let mediaStream      = null;
    let isLive           = false;
    const canvas = document.getElementById('captureCanvas');
    const ctx    = canvas.getContext('2d');

    // Unique session id for this page load
    const sessionId = 'sess_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

    // ─── Start ───────────────────────────────────────────────
    startLiveBtn.addEventListener('click', async function () {
        try {
            mediaStream = await navigator.mediaDevices.getUserMedia({
                video: { width: { ideal: 640 }, height: { ideal: 480 } }
            });
            videoFeed.srcObject = mediaStream;

            // Watch for unexpected camera disconnection
            mediaStream.getVideoTracks().forEach(function (track) {
                track.addEventListener('ended', handleStreamEnd);
            });

            startLiveBtn.disabled = true;
            stopLiveBtn.disabled  = false;
            recordingStatus.textContent = 'Recording...';
            recordingStatus.classList.add('text-red-500');
            isLive = true;

            // Capture & send a frame every 2 s
            analysisInterval = setInterval(captureAndAnalyze, 2000);
        } catch (error) {
            console.error('Error accessing camera:', error);
            if (error.name === 'NotAllowedError') {
                recordingStatus.textContent = 'Camera access denied. Please allow camera access in your browser settings.';
            } else if (error.name === 'NotFoundError') {
                recordingStatus.textContent = 'No camera found on this device.';
            } else {
                recordingStatus.textContent = 'Error starting camera: ' + error.message;
            }
            recordingStatus.classList.add('text-red-500');
        }
    });

    // ─── Stop ────────────────────────────────────────────────
    stopLiveBtn.addEventListener('click', function () { stopAnalysis(); });

    document.addEventListener('keydown', function (e) {
        if ((e.key === 'Escape' || e.key === 'Enter') && !stopLiveBtn.disabled) {
            stopAnalysis();
        }
    });

    // Cleanup on page unload
    window.addEventListener('beforeunload', function () { stopAnalysis(); });

    function handleStreamEnd() {
        if (isLive) {
            console.warn('Camera stream ended unexpectedly');
            stopAnalysis();
            recordingStatus.textContent = 'Camera disconnected';
            recordingStatus.classList.add('text-red-500');
        }
    }

    function stopAnalysis() {
        isLive = false;

        if (analysisInterval) {
            clearInterval(analysisInterval);
            analysisInterval = null;
        }
        if (mediaStream) {
            mediaStream.getTracks().forEach(function (track) {
                track.removeEventListener('ended', handleStreamEnd);
                track.stop();
            });
            mediaStream = null;
        }
        videoFeed.srcObject = null;

        startLiveBtn.disabled = false;
        stopLiveBtn.disabled  = true;
        recordingStatus.textContent = 'Not Recording';
        recordingStatus.classList.remove('text-red-500');

        // Tell the server to clean up session state
        fetch('/reset_session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        }).catch(function () { /* ignore */ });
    }

    // ─── Frame capture & analysis ────────────────────────────
    async function captureAndAnalyze() {
        if (!isLive || !mediaStream) return;

        canvas.width  = videoFeed.videoWidth  || 640;
        canvas.height = videoFeed.videoHeight || 480;
        ctx.drawImage(videoFeed, 0, 0, canvas.width, canvas.height);

        // JPEG at 70 % quality → base64
        var frameData = canvas.toDataURL('image/jpeg', 0.7);

        try {
            var response = await fetch('/analyze_frame', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ frame: frameData, session_id: sessionId })
            });

            if (!response.ok) {
                var err = await response.json();
                console.error('Analysis error:', err.error);
                return;
            }

            var result = await response.json();

            // Immediate local-stat feedback
            var stats = result.stats;
            if (stats && !result.feedback.judgment) {
                var faceIcon = stats.face_detected ? '✅' : '❌';
                var poseIcon = stats.pose_detected ? '✅' : '❌';
                eyeContactEl.textContent   = faceIcon + ' Face detected (' + stats.eye_contact_ratio + ' frames)';
                bodyLanguageEl.textContent  = poseIcon + ' Pose detected (' + stats.pose_ratio + ' frames)';
                judgmentEl.textContent      = 'Analyzing… AI feedback coming shortly';
                tipsEl.textContent          = 'Gathering data for analysis…';
            }

            // Gemini feedback when available
            var fb = result.feedback;
            if (fb && fb.judgment) {
                judgmentEl.textContent      = fb.judgment;
                eyeContactEl.textContent   = fb.eye_contact   || 'Not available';
                bodyLanguageEl.textContent  = fb.body_language || 'Not available';
                tonePaceEl.textContent      = fb.tone_pace     || 'Not available';
                tipsEl.textContent          = fb.tips          || 'Not available';
            }

            // Pulse on Gemini update
            if (result.gemini_updated) {
                [judgmentEl, eyeContactEl, bodyLanguageEl, tonePaceEl, tipsEl].forEach(function (el) {
                    el.classList.add('animate-pulse');
                    setTimeout(function () { el.classList.remove('animate-pulse'); }, 1000);
                });
            }
        } catch (error) {
            console.error('Error sending frame:', error);
        }
    }

    // ─── PDF report (unchanged logic) ────────────────────────
    document.getElementById('downloadReport').addEventListener('click', async function () {
        var jsPDF = window.jspdf.jsPDF;
        var doc   = new jsPDF();

        var today   = new Date();
        var dateStr = today.toLocaleDateString() + ' ' + today.toLocaleTimeString();

        var feedback = {};
        try {
            var res = await fetch('/live_feedback?session_id=' + sessionId);
            feedback = await res.json();
        } catch (e) {
            feedback = {
                judgment:      judgmentEl.innerText,
                eye_contact:   eyeContactEl.innerText,
                body_language: bodyLanguageEl.innerText,
                tone_pace:     tonePaceEl.innerText,
                tips:          tipsEl.innerText
            };
        }
        var judgment     = feedback.judgment      || 'Not available';
        var eyeContact   = feedback.eye_contact   || 'Not available';
        var bodyLanguage = feedback.body_language  || 'Not available';
        var tonePace     = feedback.tone_pace      || 'Not available';
        var tips         = feedback.tips           || 'Not available';

        var overallAnalysis = generateOverallAnalysis(judgment, eyeContact, bodyLanguage, tonePace, tips);

        var titleColor   = '#4F46E5';
        var headingColor = '#10B981';
        var textColor    = '#333333';

        doc.setFontSize(20);
        doc.setTextColor(titleColor);
        doc.text('Vaakpragna - Comprehensive Speech Analysis', 105, 20, { align: 'center' });

        doc.setFontSize(10);
        doc.setTextColor(100);
        doc.text('Generated on: ' + dateStr, 105, 30, { align: 'center' });
        doc.line(20, 35, 190, 35);

        doc.setFontSize(16);
        doc.setTextColor(titleColor);
        doc.text('Comprehensive Performance Summary', 20, 45);

        doc.setFontSize(12);
        doc.setTextColor(textColor);
        doc.text(overallAnalysis, 20, 55, { maxWidth: 170 });

        var yPosition = doc.splitTextToSize(overallAnalysis, 170).length * 6 + 60;
        doc.setFontSize(15);
        doc.setTextColor('#4F46E5');
        doc.text('Final Live Feedback Outcomes', 20, yPosition);
        yPosition += 8;

        function addSection(title, content) {
            doc.setFontSize(14);
            doc.setTextColor(headingColor);
            doc.text(title, 20, yPosition);
            yPosition += 7;
            doc.setFontSize(12);
            doc.setTextColor(textColor);
            var lines = doc.splitTextToSize(content, 170);
            if (yPosition + lines.length * 6 > 270) { doc.addPage(); yPosition = 20; }
            doc.text(lines, 20, yPosition);
            yPosition += lines.length * 6 + 6;
        }

        addSection('Detailed Judgment',          judgment);
        addSection('Eye Contact Analysis',       eyeContact);
        addSection('Body Language Evaluation',   bodyLanguage);
        addSection('Tone & Pace Assessment',     tonePace);
        addSection('Actionable Improvement Tips', tips);

        doc.setFontSize(10);
        doc.setTextColor(100);
        doc.text('© Vaakpragna - AI-Powered Speech Analysis', 105, 285, { align: 'center' });

        doc.save('Vaakpragna_Speech_Analysis_' + today.toISOString().slice(0, 10) + '.pdf');
    });
});

// Overall analysis builder (unchanged logic)
function generateOverallAnalysis(judgment, eyeContact, bodyLanguage, tonePace, tips) {
    return '\nThis comprehensive analysis combines all evaluation metrics to provide a holistic view of your speaking performance.\n\nKey Strengths:\n- ' +
        (judgment.includes('good') || judgment.includes('excellent') ? judgment.split('.')[0] : 'Your delivery shows potential in several areas') +
        '\n- ' + (eyeContact.includes('good') || eyeContact.includes('excellent') ? eyeContact.split('.')[0] : 'With practice, your eye contact can become more effective') +
        '\n- ' + (bodyLanguage.includes('good') || bodyLanguage.includes('excellent') ? bodyLanguage.split('.')[0] : 'Your body language has room for improvement') +
        '\n\nAreas for Development:\n- ' + (tonePace.includes('improve') ? tonePace.split('.')[0] : 'Your tone and pace are generally appropriate') +
        '\n- ' + (tips.includes('try') ? tips.split('.')[0] : 'Consider implementing the suggested improvements') +
        '\n\nRecommendations:\n1. Focus on ' + (tips.split('.')[0].toLowerCase() || 'the key areas mentioned above') +
        '\n2. Practice ' + (eyeContact.toLowerCase().includes('maintain') ? 'maintaining consistent eye contact' : 'your eye contact technique') +
        '\n3. Work on ' + (bodyLanguage.toLowerCase().includes('posture') ? 'your posture and gestures' : 'your body language awareness') +
        '\n\nFinal Assessment:\n' + (judgment || 'Your overall performance shows potential with room for growth in specific areas.') + '\n';
}
