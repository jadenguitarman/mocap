
import cv2
import sys
import time
import argparse
import os

def record_camera(index, filename, width=1280, height=720, fps=30):
    cap = cv2.VideoCapture(index)
    
    # Try to set resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    
    # Check if camera opened successfully
    if not cap.isOpened():
        print(f"Error: Could not open camera {index}")
        return

    # Define the codec and create VideoWriter object
    # using mp4v for compatibility
    fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
    out = cv2.VideoWriter(filename, fourcc, fps, (width, height))

    print(f"Recording from Camera {index} to {filename}...")
    
    # We need a way to stop. 
    # Since this is a subprocess, we can listen for a file signal or just stdin.
    # For simplicity in this "one-click" tool, we'll check for a stop file or rely on terminate() from parent.
    # But terminate() might corrupt the video.
    # Using a "stop flag" file is safer.
    
    stop_file = filename + ".stop"
    if os.path.exists(stop_file):
        os.remove(stop_file)

    frame_count = 0
    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if ret:
            # Write the frame
            out.write(frame)
            frame_count += 1
            
            # Check for stop signal
            if os.path.exists(stop_file):
                print("Stop signal received.")
                break
        else:
            print("Error reading frame.")
            break
            
    # Release everything if job is finished
    cap.release()
    out.release()
    if os.path.exists(stop_file):
        os.remove(stop_file)
        
    duration = time.time() - start_time
    print(f"Recording finished. {frame_count} frames in {duration:.2f}s ({frame_count/duration:.2f} FPS)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Record video from a camera.')
    parser.add_argument('index', type=int, help='Camera index')
    parser.add_argument('filename', type=str, help='Output filename')
    
    args = parser.parse_args()
    
    try:
        record_camera(args.index, args.filename)
    except KeyboardInterrupt:
        print("Interrupted by user.")
