import gradio as gr
from google import genai
from google.genai.types import Content, Part
import json
import yt_dlp
import subprocess
import os
import re
import shutil
import time
import asyncio
from pathlib import Path

# Gemini API key - Load from environment variable for security
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyAbOoIMpIyENKXEEAU8aBtojGX4EalO3Dw")

# Global variables
current_video_path = None
clip_suggestions = []

def clear_clips_folder():
    """Clear all files from the clips folder."""
    clips_dir = Path("downloads/clips")
    if clips_dir.exists():
        try:
            # Remove all files in the clips directory
            for file_path in clips_dir.glob("*"):
                if file_path.is_file():
                    file_path.unlink()
            return "✅ Clips folder cleared successfully!"
        except Exception as e:
            return f"❌ Error clearing clips folder: {e}"
    else:
        return "📁 Clips folder doesn't exist yet."

def refresh_clips_gallery():
    """Refresh the clips gallery by scanning the clips folder."""
    clips_dir = Path("downloads/clips")
    if clips_dir.exists():
        clip_files = list(clips_dir.glob("*.mp4"))
        return [str(clip) for clip in clip_files]
    return []

# ---- SYSTEM PROMPT ----
SYSTEM_PROMPT = """
Prompt for AI Clip‑Selection Assistant

Goal: Extract the top hook-worthy clips for a high-impact 1-minute B2B marketing video about Zycus.

Instructions:

Watch the full video transcript attentively.

Identify 3–5 high‑impact clip segments—each between 5 and 20 seconds—that work as powerful hooks or transitions in a 1-minute marketing edit.

Prioritize moments that contain:

Bold claims, surprising insights, or quantified outcomes (e.g., "we increased efficiency by 40%").

"A-ha" realizations or objections flipped.

Clear stakes emphasizing ROI or business value.

At least one clip that explicitly mentions “Zycus” early—anchor it prominently.

Exclude filler language, off-topic tangents, and hedging (“maybe,” “kind of,” prolonged pauses).

Your task:
- Watch the video transcript and identify strong hook moments.
- Output a JSON array where each item has:
  - start: float (clip start time in seconds)
  - end: float (clip end time in seconds)
  - title: short, curiosity-driven 3–7 word title
  - description: EXACTLY ONE SENTENCE (max 20 words) explaining why it's a strong hook
  - duration: float (end - start)

CRITICAL RULES:
- Description must be EXACTLY ONE SENTENCE with maximum 20 words
- NO repetitive text, NO long explanations, NO marketing analysis
- Prioritize bold claims, surprises, quantified outcomes, aha moments, objections flipped, or ROI stakes
- Ensure at least one hook explicitly mentions "Zycus" early (if it exists)
- Respect user request for number and duration of clips
- Exclude filler, tangents, and hedging
- Return ONLY valid JSON. No text outside the JSON
- NEVER repeat the same description multiple times

Example Output:

[
  {
    "start": 12.3,
    "end": 22.5,
    "title": "Zycus Cuts Procurement Costs",
    "description": "Zycus reduces procurement costs by 30%.",
    "duration": 10.2
  },
  {
    "start": 45.0,
    "end": 55.0,
    "title": "Unexpected ROI Surprise",
    "description": "ROI data creates compelling hook for continued viewing.",
    "duration": 10.0
  }
]

"""

# ---- Functions ----
def analyze_video_with_gemini(youtube_url, num_clips=5, min_dur=5, max_dur=10, custom_system_prompt=None):
    """Step 1: Analyze YouTube video with Gemini to get clip suggestions."""
    global clip_suggestions
    
    # Use custom system prompt if provided, otherwise use default
    system_prompt_to_use = custom_system_prompt.strip() if custom_system_prompt and custom_system_prompt.strip() else SYSTEM_PROMPT
    
    # Retry logic for API calls
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            # Create a fresh client for each attempt
            client = genai.Client(api_key=GEMINI_API_KEY)
            
            # Ask Gemini to process the YT video with structured JSON output
            response = client.models.generate_content(
                model="models/gemini-2.5-flash",
                contents=Content(
                    parts=[
                        Part(text=system_prompt_to_use),
                        Part(file_data={"file_uri": youtube_url}),
                        Part(text=f"Extract {num_clips} clips, each {min_dur}-{max_dur} seconds long.")
                    ]
                ),
                config={
                    "response_mime_type": "application/json",
                    "response_schema": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "start": {"type": "number"},
                                "end": {"type": "number"},
                                "description": {"type": "string"}
                            },
                            "required": ["title", "start", "end"]
                        }
                    }
                }
            )
            
            # If we get here, the API call succeeded
            break
            
        except (ConnectionResetError, ConnectionError, OSError) as e:
            if attempt < max_retries - 1:
                print(f"Connection error on attempt {attempt + 1}, retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
                continue
            else:
                return f"❌ Connection failed after {max_retries} attempts: {e}"
        except Exception as e:
            return f"❌ API Error: {e}"
        
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
            # Get timestamps directly from AI output (should already be in seconds)
            start_time = clip["start"]
            end_time = clip["end"]
            
            # Use timestamps as-is since AI is instructed to output in seconds
            start_time_seconds = start_time
            end_time_seconds = end_time
            
            # Debug logging
            print(f"Clip {i+1}: AI output start={start_time}, end={end_time}")
            print(f"Using for ffmpeg: start={start_time_seconds}, end={end_time_seconds}")
            
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
    gr.Markdown("# 🎬 YouTube Marketing Clip Extractor & Downloader", elem_id="title")
    
    # Input Controls Row
    with gr.Row():
        with gr.Column(scale=1):
            youtube_url = gr.Textbox(label="YouTube Video URL")
            
        with gr.Column(scale=1):
            with gr.Row():
                num_clips = gr.Slider(1, 10, value=5, step=1, label="Number of Clips")
                min_dur = gr.Slider(3, 20, value=5, step=1, label="Min Duration (sec)")
                max_dur = gr.Slider(5, 60, value=10, step=1, label="Max Duration (sec)")
    
    # System Prompt Input (Full Width)
    system_prompt_input = gr.Textbox(
        label="System Prompt (Optional - Leave empty for default)",
        placeholder="Enter your custom system prompt here, or leave empty to use the default Zycus-focused prompt...",
        lines=4,
        value=""
    )
    
    # Action Buttons
    with gr.Row():
        analyze_btn = gr.Button("🧠 Analyze with Gemini", variant="primary", scale=1)
        extract_btn = gr.Button("✂️ Extract Clips", variant="primary", scale=1)
        clear_btn = gr.Button("🗑️ Clear Clips", variant="secondary", scale=1)
        refresh_btn = gr.Button("🔄 Refresh Gallery", variant="secondary", scale=1)
    
    # Status outputs
    with gr.Row():
        analyze_output = gr.Textbox(label="Gemini Analysis Results", lines=6, scale=1)
        extract_status = gr.Textbox(label="Clip Extraction Status", lines=6, scale=1)
    
    # Clips Gallery - Full Width and Centered
    gr.Markdown("## 🎥 Generated Video Clips", elem_id="clips-title")
    clips_gallery = gr.Gallery(
        label="Video Clips",
        show_label=False,
        columns=3,
        rows=2,
        height=600,
        allow_preview=True,
        container=True,
        elem_id="clips-gallery"
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
    
    clear_btn.click(
        clear_clips_folder,
        inputs=[],
        outputs=extract_status
    )
    
    refresh_btn.click(
        refresh_clips_gallery,
        inputs=[],
        outputs=clips_gallery
    )

if __name__ == "__main__":
    demo.launch(share=True)
