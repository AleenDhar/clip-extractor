import gradio as gr
from google import genai
from google.genai.types import Content, Part
import json
import yt_dlp
import subprocess
import os
from pathlib import Path

# Init Gemini client
client = genai.Client(api_key="AIzaSyCzVXZ6jq3Z80W_QOG4lqXidjtk6DDKVkA")

# Global variables
current_video_path = None
clip_suggestions = []

# ---- SYSTEM PROMPT ----
SYSTEM_PROMPT = """
You are an AI assistant that analyzes YouTube videos (webinars, interviews, product demos, or panels) 
to extract high-engagement clips for marketing videos.

Your task:
- Watch the video transcript and identify strong hook moments.
- Output a JSON array where each item has:
  - start: float (clip start time in seconds)
  - end: float (clip end time in seconds)
  - title: short, curiosity-driven 3–7 word title
  - description: 1 sentence that explains why it’s a strong hook
  - duration: float (end - start)

Rules:
- Prioritize bold claims, surprises, quantified outcomes, aha moments, objections flipped, or ROI stakes.
- Ensure at least one hook explicitly mentions “Zycus” early (if it exists).
- Respect user request for number and duration of clips.
- Exclude filler, tangents, and hedging.
- Return ONLY valid JSON. No text outside the JSON.
"""

# ---- Functions ----
def download_video(youtube_url):
    """Download video from YouTube."""
    global current_video_path
    
    if not youtube_url:
        return "❌ Please enter a YouTube URL", None
    
    try:
        download_dir = Path("downloads")
        download_dir.mkdir(exist_ok=True)
        
        opts = {
            'format': 'best[ext=mp4]',
            'outtmpl': str(download_dir / "%(title)s.%(ext)s"),
        }
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
            filepath = Path(ydl.prepare_filename(info))
            current_video_path = str(filepath)
            return f"✅ Downloaded: {filepath.name}", str(filepath)
    except Exception as e:
        return f"❌ Error downloading: {e}", None

def extract_clips(youtube_url, num_clips=5, min_dur=5, max_dur=10):
    """Extract clip suggestions using Gemini."""
    global clip_suggestions
    
    try:
        # Ask Gemini to process the YT video
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=Content(
                parts=[
                    Part(text=SYSTEM_PROMPT),
                    Part(file_data={"file_uri": youtube_url}),
                    Part(text=f"Extract {num_clips} clips, each {min_dur}-{max_dur} seconds long.")
                ]
            )
        )
        
        # Parse JSON response
        try:
            clip_suggestions = json.loads(response.text)
            return f"✅ Found {len(clip_suggestions)} clip suggestions:\n\n{response.text}"
        except json.JSONDecodeError:
            return f"❌ Could not parse JSON response:\n{response.text}"
            
    except Exception as e:
        return f"Error: {e}"

def create_clips():
    """Create actual video clips from suggestions."""
    global current_video_path, clip_suggestions
    
    if not current_video_path:
        return "❌ No video downloaded. Please download video first.", []
    
    if not clip_suggestions:
        return "❌ No clip suggestions. Please extract clips first.", []
    
    clips_dir = Path("downloads/clips")
    clips_dir.mkdir(exist_ok=True)
    
    created_clips = []
    errors = []
    
    for i, clip in enumerate(clip_suggestions):
        try:
            start_time = clip["start"]
            end_time = clip["end"]
            title = clip.get("title", f"Clip {i+1}")
            
            # Create safe filename
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()[:30]
            clip_filename = f"clip_{i+1}_{safe_title}_{start_time}_{end_time}.mp4"
            output_path = clips_dir / clip_filename
            
            # Use ffmpeg with re-encoding for precise clip extraction
            cmd = [
                'ffmpeg', 
                '-ss', str(start_time),
                '-i', current_video_path,
                '-t', str(end_time - start_time),
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-preset', 'fast',
                '-crf', '23',
                '-avoid_negative_ts', 'make_zero',
                '-force_key_frames', 'expr:gte(t,0)',
                str(output_path),
                '-y'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                created_clips.append(str(output_path))
            else:
                errors.append(f"Clip {i+1}: {result.stderr}")
                
        except Exception as e:
            errors.append(f"Clip {i+1}: {e}")
    
    result_text = f"✅ Created {len(created_clips)} clips successfully!\n\n"
    if errors:
        result_text += f"❌ Errors ({len(errors)}):\n"
        for error in errors:
            result_text += f"• {error}\n"
    
    return result_text, created_clips

# ---- Gradio UI ----
with gr.Blocks() as demo:
    gr.Markdown("## 🎬 YouTube Marketing Clip Extractor & Downloader")

    with gr.Row():
        with gr.Column(scale=2):
            youtube_url = gr.Textbox(label="YouTube Video URL")
            
            with gr.Row():
                num_clips = gr.Slider(1, 10, value=5, step=1, label="Number of Clips")
            with gr.Row():
                min_dur = gr.Slider(3, 20, value=5, step=1, label="Min Duration (sec)")
                max_dur = gr.Slider(5, 60, value=10, step=1, label="Max Duration (sec)")
            
            # Buttons
            with gr.Row():
                download_btn = gr.Button("📥 Download Video", variant="secondary")
                extract_btn = gr.Button("🧠 Extract Hooks", variant="primary")
                create_btn = gr.Button("✂️ Create Clips", variant="primary")
            
            # Status outputs
            download_status = gr.Textbox(label="Download Status", lines=2)
            extract_output = gr.Textbox(label="Extracted Clips JSON", lines=10)
            create_status = gr.Textbox(label="Clip Creation Status", lines=5)
        
        with gr.Column(scale=1):
            gr.Markdown("### 🎥 Created Clips")
            clips_gallery = gr.Gallery(
                label="Download Clips",
                show_label=True,
                columns=1,
                rows=5,
                height="auto",
                allow_preview=True
            )
    
    # Connect functions
    download_btn.click(
        download_video,
        inputs=youtube_url,
        outputs=[download_status, gr.State()]
    )
    
    extract_btn.click(
        extract_clips,
        inputs=[youtube_url, num_clips, min_dur, max_dur],
        outputs=extract_output
    )
    
    create_btn.click(
        create_clips,
        outputs=[create_status, clips_gallery]
    )

# Launch
if __name__ == "__main__":
    demo.launch()
