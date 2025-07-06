#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hindi Text → Video Web API (Render-compatible)
"""

from flask import Flask, request, send_file, render_template_string, jsonify
import os
import uuid
import textwrap
import subprocess
import threading
import time
from gtts import gTTS
from pydub import AudioSegment

app = Flask(__name__)

# ========== CONFIGURATION ==========
FFMPEG_BIN = "./bin/ffmpeg"  # Use local FFmpeg binary
BACKGROUND_IMAGE = "background.jpg"
FONT_SIZE = 28
WORDS_PER_CHUNK = 8
MAX_LINE_CHARS = 45
FONT_COLOR = "#FFFFFF"
OUTLINE_COLOR = "#000000"
OUTLINE_WIDTH = 1
PORT = int(os.getenv("PORT", 10000))
CLEANUP_DELAY = 5
# ===================================

HTML_FORM = """
<!doctype html>
<title>Hindi Text → Video</title>
<h2>Hindi Text → Sub‑titled Video Converter</h2>
<form method="post">
  <textarea name="text" rows="6" cols="80" placeholder="हिंदी टेक्स्ट यहाँ लिखें" required></textarea><br><br>
  <button type="submit">Convert ➜ Video</button>
</form>
{% if error %}<p style="color:red;">{{ error }}</p>{% endif %}
<p style="font-size:small;color:#666;">Powered by gTTS · FFmpeg · Flask</p>
"""

def hms_ms(ms: int) -> str:
    h, rem = divmod(ms // 1000, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02}:{m:02}:{s:02},{ms%1000:03}"

def run_ffmpeg(cmd):
    subprocess.run(cmd, check=True, capture_output=True)

def build_video(text: str) -> str:
    uid = uuid.uuid4().hex[:8]
    mp3 = f"{uid}.mp3"
    srt = f"{uid}.srt"
    mp4 = f"{uid}.mp4"

    gTTS(text=text, lang="hi").save(mp3)
    audio = AudioSegment.from_file(mp3)
    total_ms = len(audio)

    words = text.split()
    chunks = [" ".join(words[i:i+WORDS_PER_CHUNK]) for i in range(0, len(words), WORDS_PER_CHUNK)]
    slice_ms = total_ms // len(chunks)

    with open(srt, "w", encoding="utf-8") as f:
        for i, chunk in enumerate(chunks, 1):
            start = (i-1) * slice_ms
            end = total_ms if i == len(chunks) else i * slice_ms
            f.write(f"{i}\n{hms_ms(start)} --> {hms_ms(end)}\n{textwrap.fill(chunk, MAX_LINE_CHARS)}\n\n")

    ffmpeg_cmd = [
        FFMPEG_BIN, "-y", "-loop", "1", "-i", BACKGROUND_IMAGE, "-i", mp3,
        "-vf", f"subtitles={srt}:force_style='Fontsize={FONT_SIZE},PrimaryColour={FONT_COLOR},"
               f"OutlineColour={OUTLINE_COLOR},Outline={OUTLINE_WIDTH},Alignment=10,MarginV=30'",
        "-c:v", "libx264", "-preset", "medium", "-tune", "stillimage",
        "-c:a", "copy", "-pix_fmt", "yuv420p", "-shortest", mp4
    ]
    run_ffmpeg(ffmpeg_cmd)
    os.remove(mp3)
    os.remove(srt)

    return mp4

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        text = request.form.get("text", "").strip()
        if not text:
            return render_template_string(HTML_FORM, error="टेक्स्ट चाहिए!")

        try:
            video_path = build_video(text)
        except subprocess.CalledProcessError:
            return render_template_string(HTML_FORM, error="FFmpeg error")

        request.video_path = video_path
        return send_file(video_path, as_attachment=True, download_name="hindi_video.mp4")

    return render_template_string(HTML_FORM, error=None)

@app.post("/api")
def api():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 415
    text = request.json.get("text", "").strip()
    if not text:
        return jsonify({"error": "'text' field is required"}), 400
    try:
        video_path = build_video(text)
    except subprocess.CalledProcessError:
        return jsonify({"error": "FFmpeg processing failed"}), 500
    request.video_path = video_path
    return send_file(video_path,
                     as_attachment=True,
                     download_name="hindi_video.mp4",
                     mimetype="video/mp4")

@app.after_request
def delayed_cleanup(response):
    video_path = getattr(request, "video_path", None)

    def _delete(path):
        time.sleep(CLEANUP_DELAY)
        try:
            if os.path.exists(path):
                os.remove(path)
                print(f"🧹 Deleted: {path}")
        except Exception as e:
            print(f"Cleanup error: {e}")

    if response.status_code == 200 and video_path:
        threading.Thread(target=_delete, args=(video_path,), daemon=True).start()

    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
