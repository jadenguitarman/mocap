
import os
import cv2
import time
import argparse
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
    
    # 1. Intrinsic Calibration
    for idx in cam_indices:
        cam_dir = os.path.join(image_dir, f"cam{idx}")
        images = [os.path.join(cam_dir, f) for f in os.listdir(cam_dir) if f.endswith(".jpg")]
        
        print(f"Calibrating Intrinsics for Cam {idx} ({len(images)} images)...")
        res = calibrator.calibrate_intrinsics(images)
        if res:
            mtx, dist, ret = res
            results[f"mtx_{idx}"] = mtx
            results[f"dist_{idx}"] = dist
            results[f"ret_{idx}"] = ret
            print(f"  > Error: {ret}")
        else:
            print(f"  > Failed to calibrate Cam {idx}")

    # 2. Extrinsic Calibration (Simplified)
    # We use the FIRST image set (img_0000.jpg) as the "World Origin" anchor.
    # The board must be visible in all cameras for this frame.
    print("Calibrating Extrinsics (using img_0000.jpg)...")
    for idx in cam_indices:
        img_path = os.path.join(image_dir, f"cam{idx}", "img_0000.jpg")
        if os.path.exists(img_path) and f"mtx_{idx}" in results:
            rvec, tvec = calibrator.estimate_pose(img_path, results[f"mtx_{idx}"], results[f"dist_{idx}"])
            if rvec is not None:
                # Store as 4x4 matrix or rvec/tvec
                results[f"rvec_{idx}"] = rvec
                results[f"tvec_{idx}"] = tvec
                print(f"  > Cam {idx} Pose Found.")
            else:
                print(f"  > Cam {idx} Pose Failed (Board not found in first image).")
        else:
            print(f"  > Skipping Extrinsics for Cam {idx} (Missing file or intrinsics).")

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
