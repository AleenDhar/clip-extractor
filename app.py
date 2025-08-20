import gradio as gr
from google import genai
from google.genai.types import Content, Part
import json
import yt_dlp
import subprocess
import os
import re
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
def analyze_video_with_gemini(youtube_url, num_clips=5, min_dur=5, max_dur=10, custom_system_prompt=None):
    """Step 1: Analyze YouTube video with Gemini to get clip suggestions."""
    global clip_suggestions
    
    # Use custom system prompt if provided, otherwise use default
    system_prompt_to_use = custom_system_prompt.strip() if custom_system_prompt and custom_system_prompt.strip() else SYSTEM_PROMPT
    
    try:
        # Ask Gemini to process the YT video
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=Content(
                parts=[
                    Part(text=system_prompt_to_use),
                    Part(file_data={"file_uri": youtube_url}),
                    Part(text=f"Extract {num_clips} clips, each {min_dur}-{max_dur} seconds long.")
                ]
            )
        )
        
        # Parse JSON response
        try:
            # First try to parse the entire response as JSON
            try:
                clip_suggestions = json.loads(response.text)
                return f"✅ Found {len(clip_suggestions)} clip suggestions:\n\n{response.text}"
            except json.JSONDecodeError:
                # If that fails, try to extract JSON array from markdown code blocks
                json_match = re.search(r'```json\s*(\[.*?\])\s*```', response.text, re.DOTALL)
                if json_match:
                    clip_suggestions = json.loads(json_match.group(1))
                    return f"✅ Found {len(clip_suggestions)} clip suggestions:\n\n{json_match.group(1)}"
                else:
                    # Try to find any JSON array in the response
                    json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
                    if json_match:
                        clip_suggestions = json.loads(json_match.group())
                        return f"✅ Found {len(clip_suggestions)} clip suggestions:\n\n{json_match.group()}"
                    else:
                        return f"❌ Could not find JSON array in response:\n{response.text}"
        except json.JSONDecodeError as e:
            return f"❌ Could not parse JSON response: {e}\n{response.text}"
            
    except Exception as e:
        return f"Error: {e}"

def extract_clips(youtube_url):
    """Step 2: Download video and create clips from Gemini suggestions."""
    global current_video_path, clip_suggestions
    
    if not clip_suggestions:
        return "❌ No clip suggestions found. Please analyze video with Gemini first.", []
    
    # First download the video
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
    except Exception as e:
        return f"❌ Error downloading video: {e}", []
    
    # Then create clips from suggestions
    clips_dir = Path("downloads/clips")
    clips_dir.mkdir(exist_ok=True)
    
    created_clips = []
    errors = []
    
    for i, clip in enumerate(clip_suggestions):
        try:
            # Convert minutes to seconds if needed
            start_time = clip["start"]
            end_time = clip["end"]
            
            # Check if timestamps are in minutes (likely if values are small like 2.21, 3.45)
            if start_time < 60 and end_time < 60:
                # Convert minutes to seconds
                start_time_seconds = start_time * 60
                end_time_seconds = end_time * 60
            else:
                # Already in seconds
                start_time_seconds = start_time
                end_time_seconds = end_time
            
            title = clip.get("title", f"Clip {i+1}")
            
            # Create safe filename
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()[:30]
            clip_filename = f"clip_{i+1}_{safe_title}_{start_time}_{end_time}.mp4"
            output_path = clips_dir / clip_filename
            
            # Use ffmpeg with re-encoding for precise clip extraction
            cmd = [
                'ffmpeg', 
                '-ss', str(start_time_seconds),
                '-i', current_video_path,
                '-t', str(end_time_seconds - start_time_seconds),
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
    
    result_text = f"✅ Downloaded video and created {len(created_clips)} clips successfully!\n\n"
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
            
            # System Prompt Input
            system_prompt_input = gr.Textbox(
                label="System Prompt (Optional - Leave empty for default)",
                placeholder="Enter your custom system prompt here, or leave empty to use the default Zycus-focused prompt...",
                lines=6,
                value=""
            )
            
            with gr.Row():
                num_clips = gr.Slider(1, 10, value=5, step=1, label="Number of Clips")
            with gr.Row():
                min_dur = gr.Slider(3, 20, value=5, step=1, label="Min Duration (sec)")
                max_dur = gr.Slider(5, 60, value=10, step=1, label="Max Duration (sec)")
            
            # Buttons
            with gr.Row():
                analyze_btn = gr.Button("🧠 Analyze with Gemini", variant="primary")
                extract_btn = gr.Button("✂️ Extract Clips", variant="primary")
            
            # Status outputs
            analyze_output = gr.Textbox(label="Gemini Analysis Results", lines=10)
            extract_status = gr.Textbox(label="Clip Extraction Status", lines=5)
        
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
    analyze_btn.click(
        analyze_video_with_gemini,
        inputs=[youtube_url, num_clips, min_dur, max_dur, system_prompt_input],
        outputs=analyze_output
    )
    
    extract_btn.click(
        extract_clips,
        inputs=youtube_url,
        outputs=[extract_status, clips_gallery]
    )

# Launch
if __name__ == "__main__":
    demo.launch(share=True)
