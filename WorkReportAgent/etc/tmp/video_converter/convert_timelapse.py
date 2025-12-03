import os
import subprocess
import sys
import glob
import json

def get_video_info(filepath):
    """Get frame rate and bitrate of the video using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate,bit_rate:format=bit_rate",
        "-of", "json",
        filepath
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        if not data.get('streams'):
            print(f"No video stream found in {filepath}")
            return None, None

        # Get FPS
        r_frame_rate = data['streams'][0].get('r_frame_rate')
        fps = 0
        if r_frame_rate:
            num, den = map(int, r_frame_rate.split('/'))
            fps = num / den
        
        # Get Bitrate (try stream first, then format)
        bit_rate = data['streams'][0].get('bit_rate')
        if not bit_rate and 'format' in data:
            bit_rate = data['format'].get('bit_rate')
        
        bit_rate = int(bit_rate) if bit_rate else 0
            
        return fps, bit_rate
    except Exception as e:
        print(f"Error getting info for {filepath}: {e}")
        return None, None

def convert_video(input_path, output_path):
    """Convert video to timelapse using ffmpeg."""
    fps, original_bitrate = get_video_info(input_path)
    if fps is None:
        return False

    speed_factor = fps / 2.0
    print(f"Processing {os.path.basename(input_path)}")
    print(f"Original FPS: {fps:.2f}, Bitrate: {original_bitrate/1000:.0f}k, Speed Factor: {speed_factor:.2f}x")

    # Investigate Result:
    # The input video has a very low bitrate (~200kbps) because it is static (screen recording).
    # When sped up (e.g., 12x), the temporal redundancy is lost (scenes change instantly).
    # A low fixed bitrate (e.g., 400-600k) causes severe blocking because the encoder
    # cannot compress these rapid changes efficiently with such a small budget.
    # Solution: Use CRF (Constant Rate Factor) to maintain visual quality regardless of motion complexity.
    # Also, we must set a target output framerate (e.g., original fps). Without this, 'setpts' keeps all input frames
    # but plays them at x times the speed, resulting in absurd framerates (e.g., 300fps) which players handle poorly
    # and which waste bitrate on frames the eye cannot see.
    
    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-filter:v", f"setpts=PTS/{speed_factor},fps={fps}", # Keep original FPS to avoid dropping/duplicating frames unnecessarily
        "-c:v", "libx264",
        "-crf", "28",          # Increase CRF to reduce file size (standard range 18-28, higher is smaller/lower quality)
        "-preset", "veryslow", # Maximize compression efficiency to reduce file size
        "-an",
        output_path
    ]
    
    print(f"Running command: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True)
        print(f"Successfully converted: {input_path} -> {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error converting {input_path}: {e}")
        return False

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir = os.path.join(base_dir, "input")
    output_dir = os.path.join(base_dir, "output")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    video_extensions = ['*.mp4', '*.mov', '*.avi', '*.mkv']
    input_files = []
    for ext in video_extensions:
        input_files.extend(glob.glob(os.path.join(input_dir, ext)))

    if not input_files:
        print(f"No input files found in {input_dir}")
        return

    for input_path in input_files:
        filename = os.path.basename(input_path)
        output_path = os.path.join(output_dir, filename)
        convert_video(input_path, output_path)

if __name__ == "__main__":
    main()
