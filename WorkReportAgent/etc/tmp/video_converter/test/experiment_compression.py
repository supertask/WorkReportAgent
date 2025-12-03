import os
import subprocess
import json

def get_video_info(filepath):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate", "-of", "json", filepath
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        r_frame_rate = data['streams'][0].get('r_frame_rate')
        if r_frame_rate:
            num, den = map(int, r_frame_rate.split('/'))
            return num / den
    except:
        pass
    return None

def convert_experiment(input_path, output_dir, codec, crf, preset="medium"):
    filename = os.path.basename(input_path)
    name, ext = os.path.splitext(filename)
    output_path = os.path.join(output_dir, f"{name}_{codec}_crf{crf}{ext}")
    
    fps = get_video_info(input_path)
    if not fps: return

    speed_factor = fps / 2.0 # 12x speed roughly (based on previous context, but wait... previous code used fps/2.0 which is strange logic for 12x. 
    # The previous code: speed_factor = fps / 2.0. 
    # If fps is 24, speed_factor is 12. Correct.
    
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter:v", f"setpts=PTS/{speed_factor},fps={fps}",
        "-c:v", codec,
        "-crf", str(crf),
        "-preset", preset,
        "-an",
        output_path
    ]
    
    if codec == "libx265":
        cmd.extend(["-tag:v", "hvc1"])

    print(f"Testing {codec} CRF {crf}...")
    subprocess.run(cmd, check=True, capture_output=True) # capture output to keep terminal clean
    
    size = os.path.getsize(output_path)
    print(f"-> Size: {size/1024/1024:.2f} MB")
    return size

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(base_dir, "input/Rhino 3D For Architecture in 2025 - Full Advanced Course.mp4")
    output_dir = os.path.join(base_dir, "output_experiment")
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Baseline (Current Best)
    # H.264 CRF 28 Veryslow
    # We will test:
    # 1. H.264 CRF 32 (Lower quality)
    # 2. H.265 CRF 28 (Better codec)
    # 3. H.265 CRF 32 (Better codec + Lower quality)
    
    convert_experiment(input_path, output_dir, "libx264", 32, "veryslow")
    convert_experiment(input_path, output_dir, "libx265", 28, "medium") # x265 is slow, so use medium
    convert_experiment(input_path, output_dir, "libx265", 32, "medium")

if __name__ == "__main__":
    main()

