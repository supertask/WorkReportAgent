import os
import subprocess
import sys
import glob
import json
import yaml

def load_config():
    """Load configuration from config.yml."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yml")
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading config.yml: {e}")
        # Return default values if config fails
        return {
            "compression": {
                "crf": 28,
                "preset": "veryslow",
                "codec": "libx264"
            },
            "timelapse": {
                "speed_divisor": 2.0,
                "output_fps": "auto"
            }
        }

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

def convert_video(input_path, output_path, config):
    """Convert video to timelapse using ffmpeg."""
    fps, original_bitrate = get_video_info(input_path)
    if fps is None:
        return False

    # Get settings from config
    comp = config.get('compression', {})
    time_cfg = config.get('timelapse', {})
    
    crf = comp.get('crf', 28)
    preset = comp.get('preset', 'veryslow')
    codec = comp.get('codec', 'libx264')
    
    speed_divisor = time_cfg.get('speed_divisor', 2.0)
    output_fps = time_cfg.get('output_fps', 'auto')

    speed_factor = fps / float(speed_divisor)
    
    # Determine FPS for filter
    if output_fps == "auto":
        filter_fps = fps
    else:
        filter_fps = float(output_fps)

    print(f"Processing {os.path.basename(input_path)}")
    print(f"Original FPS: {fps:.2f}, Bitrate: {original_bitrate/1000:.0f}k, Speed Factor: {speed_factor:.2f}x")
    print(f"Settings: Codec={codec}, CRF={crf}, Preset={preset}, Output FPS={filter_fps:.2f}")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-filter:v", f"setpts=PTS/{speed_factor},fps={filter_fps}",
        "-c:v", codec,
        "-crf", str(crf),
        "-preset", preset,
        "-an",
        output_path
    ]
    
    # Add tag for H.265 compatibility if needed (Mac/QuickTime friendly)
    if codec == "libx265":
        cmd.extend(["-tag:v", "hvc1"])
    
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
    
    config = load_config()

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
        convert_video(input_path, output_path, config)

if __name__ == "__main__":
    main()
