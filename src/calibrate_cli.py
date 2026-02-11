
import os
import cv2
import time
import argparse
import requests
from processing.calibrate import CameraCalibrator
from utils.config import config


def ensure_dir(d):
    if not os.path.exists(d):
        os.makedirs(d)

def capture_calibration_images(cam_indices, output_dir="calibration_images", num_images=20, delay=2.0):
    print(f"Starting Multi-Cam Calibration Capture for cameras: {cam_indices}")
    print(f"Will capture {num_images} images with {delay}s delay.")
    print("Press 'q' to quit early.")
    
    ensure_dir(output_dir)
    
    caps = {}
    for idx in cam_indices:
        cap = cv2.VideoCapture(idx)
        # Set res from config
        width = config.get("Camera", {}).get("width", 1280)
        height = config.get("Camera", {}).get("height", 720)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        
        if cap.isOpened():
            caps[idx] = cap
        else:
            print(f"Error: Camera {idx} failed to open.")
            return False

    # Create subdirs
    for idx in cam_indices:
        ensure_dir(os.path.join(output_dir, f"cam{idx}"))

    count = 0
    last_cap_time = time.time()
    
    try:
        while count < num_images:
            frames = {}
            # Read all frames
            for idx, cap in caps.items():
                ret, frame = cap.read()
                if ret:
                    frames[idx] = frame
            
            # Show preview of first cam
            if cam_indices[0] in frames:
                cv2.imshow("Calibration Capture (Cam 0)", frames[cam_indices[0]])
                
            # Check timer
            if time.time() - last_cap_time > delay:
                print(f"Capturing set {count+1}/{num_images}...")
                for idx, frame in frames.items():
                    fname = os.path.join(output_dir, f"cam{idx}", f"img_{count:04d}.jpg")
                    cv2.imwrite(fname, frame)
                
                # Trigger Mobile Capture via Server
                try:
                    # Assuming server is running local
                    requests.post("http://127.0.0.1:5000/api/trigger_calibration", json={'count': count})
                except Exception as e:
                    print(f"Failed to trigger mobile sync: {e}")

                count += 1
                last_cap_time = time.time()
                # Flash effect or sound here would be nice

            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    finally:
        for cap in caps.values():
            cap.release()
        cv2.destroyAllWindows()
        
    print("Capture finished.")
    return True

def run_calibration(cam_indices, image_dir="calibration_images", output_file="calibration.npz"):
    
    calib_config = config.get("Calibration", {})
    rows = calib_config.get("rows", 7)
    cols = calib_config.get("columns", 5)
    sq_len = calib_config.get("square_length", 0.04)
    mk_len = calib_config.get("marker_length", 0.02)
    
    calibrator = CameraCalibrator(rows, cols, sq_len, mk_len)
    
    results = {}
    
    results = {}
    
    # Scan for ALL camera folders (camX and mobile_X)
    # return list of folders
    subdirs = [f.path for f in os.scandir(image_dir) if f.is_dir()]
    
    # 1. Intrinsic Calibration
    for cam_dir in subdirs:
        dirname = os.path.basename(cam_dir) # e.g. cam0 or mobile_12345
        
        # Identifier
        # We use the folder name as the ID suffix
        # e.g. mtx_cam0, mtx_mobile_12345
        
        cam_id = dirname 
        
        images = [os.path.join(cam_dir, f) for f in os.listdir(cam_dir) if f.startswith("img_") and f.endswith(".jpg")]
        if not images:
            continue
            
        print(f"Calibrating Intrinsics for {cam_id} ({len(images)} images)...")
        res = calibrator.calibrate_intrinsics(images)
        if res:
            mtx, dist, ret = res
            results[f"mtx_{cam_id}"] = mtx
            results[f"dist_{cam_id}"] = dist
            results[f"ret_{cam_id}"] = ret
            print(f"  > Error: {ret}")
        else:
            print(f"  > Failed to calibrate {cam_id}")

    # 2. Extrinsic Calibration (Simplified)
    # We use the FIRST image set (img_0000.jpg) as the "World Origin" anchor.
    # The board must be visible in all cameras for this frame.
    print("Calibrating Extrinsics (using img_0000.jpg)...")
    
    for cam_dir in subdirs:
        cam_id = os.path.basename(cam_dir)
        img_path = os.path.join(cam_dir, "img_0000.jpg")
        
        if os.path.exists(img_path) and f"mtx_{cam_id}" in results:
            rvec, tvec = calibrator.estimate_pose(img_path, results[f"mtx_{cam_id}"], results[f"dist_{cam_id}"])
            if rvec is not None:
                # Store as 4x4 matrix or rvec/tvec
                results[f"rvec_{cam_id}"] = rvec
                results[f"tvec_{cam_id}"] = tvec
                print(f"  > {cam_id} Pose Found.")
            else:
                print(f"  > {cam_id} Pose Failed (Board not found in first image).")
        else:
            print(f"  > Skipping Extrinsics for {cam_id} (Missing file or intrinsics).")


    # Save
    import numpy as np
    np.savez(output_file, **results)
    print(f"Calibration saved to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true", help="Run capture sequence first")
    parser.add_argument("--process", action="store_true", help="Run calibration processing")
    args = parser.parse_args()
    
    # Defaults
    cams = config.get("Camera", {}).get("indices", [0, 1])
    save_path = config.get("Calibration", {}).get("save_path", "calibration.npz")
    
    if args.capture:
        capture_calibration_images(cams)
        
    if args.process:
        run_calibration(cams, output_file=save_path)
        
    if not args.capture and not args.process:
        print("Please specify --capture or --process (or both).")
