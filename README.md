# Local Multi-Cam Mocap Tool - Instruction Manual

## 1. Project Overview

This tool provides a local, low-friction pipeline for markerless motion capture using multiple webcams. It is designed to capture synchronized video and audio, process it using OpenPose and DLT triangulation, and export the resulting 3D animation data directly into Unreal Engine 5 via CSV Data Tables.

### Key Features
- **Concurrent Recording**: Captures from 2-6 webcams simultaneously.
- **Audio Sync**: Uses an audio "clap" spike to synchronize footage.
- **iPhone Face Sync**: Triggers Live Link Face app recording via OSC.
- **Unreal Engine Control**: Triggers Take Recorder in UE5 via OSC.
- **Automated Pipeline**: 
  - Runs OpenPose on recorded videos.
  - Triangulates 2D points to 3D world space.
  - Applies One Euro Filter smoothing.
  - Exports to CSV for immediate use in Unreal.

---

## 2. System Requirements

### Hardware
- **PC**: Windows 10/11 (Linux/Mac support experimental).
- **GPU**: NVIDIA GPU with 8GB+ VRAM recommended (for OpenPose).
- **Cameras**: 2 or more webcams (Logitech C920, Brio, etc.) connected via USB.
  - *Tip*: Ensure USB bandwidth is sufficient. Use multiple controllers if possible.
- **iPhone**: For facial capture (optional), running Live Link Face.
- **Calibration Board**: ChArUco board printed and mounted on a flat surface.

### Software
- **Python 3.8+**
- **Unreal Engine 5.0+** (tested with 5.3/5.4)
- **OpenPose**: Download and build the binaries (or use pre-built Windows binaries).
  - *Path*: The tool expects `bin/OpenPoseDemo.exe` by default.

---

## 3. Installation

1.  **Clone the Repository**:
    ```bash
    git clone <repo_url>
    cd mocap
    ```

2.  **Install Python Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
    *Dependencies include: `customtkinter`, `opencv-python`, `numpy`, `scipy`, `python-osc`, `pyaudio`.*

3.  **Install OpenPose**:
    -   Download OpenPose from the [official repository](https://github.com/CMU-Perceptual-Computing-Lab/openpose).
    -   Place the `OpenPoseDemo.exe` and `models/` folder in a known location.
    -   **Configuration**: Update `src/processing/pipeline.py` with the absolute path to your `OpenPoseDemo.exe` if it's not in `bin/`.

4.  **Unreal Engine Verification**:
    -   Ensure you have the "Python Editor Script Plugin", "OSC", and "Takes" plugins enabled.

---

## 4. Configuration

### Network Setup (OSC)
To enable communication between the PC, iPhone, and Unreal Engine:
1.  **Find your PC's IP Address**: Run `ipconfig` in CMD.
2.  **iPhone Setup**:
    -   Open Live Link Face.
    -   Go to Settings > OSC.
    -   Set **Target IP** to your PC's IP.
    -   Set **Port** to `8000` (Unreal's listener).
3.  **Tool Configuration**:
    -   Open `src/osc/client.py` and `src/gui/app.py`.
    -   Update `iphone_ip` to your iPhone's IP address.
    -   Ensure `unreal_ip` is `127.0.0.1` (Localhost) and port `8000`.

### Camera Setup
-   Identify your camera indices (`0, 1, 2...`).
-   You can check these by running a simple OpenCV script or testing in the GUI.

---

## 5. Unreal Engine Integration

A detailed setup guide is available in `unreal/UNREAL_SETUP.md`.

### Quick Summary
1.  **Orchestrator Blueprint**: Create `BP_MocapOrchestrator` to listen for OSC triggers (`/recStart`, `/recStop`).
2.  **Watcher Script**: Add `unreal/mocap_watcher.py` to your Unreal Project's Startup Scripts (Project Settings > Python).
    -   This script automatically imports new CSVs from the `MocapImports` folder into a Data Table (`DT_MocapLive`).
3.  **Control Rig**:
    -   Create a Control Rig for your character.
    -   Add logic to read from `DT_MocapLive` based on the current timeline time.
    -   Drive bone controls using the imported coordinate data.

---

## 6. Usage Workflow

### Step A: Calibration (Important)
*Before recording, you must calibrate your multi-camera setup.*
1.  **Capture**: Take synchronized photos or a short video of a ChArUco board visible to all cameras.
2.  **Run Calibration**:
    -   Currently, the calibration logic is in `src/processing/calibrate.py`.
    -   You may need to write a small script to call `calibrate_intrinsics` and save the `calibration.npz` file.
    -   *Note*: The pipeline currently looks for `calibration.npz` (to be implemented fully).

### Step B: Recording
1.  **Launch the Controller**:
    ```bash
    python src/main.py
    ```
2.  **Enter Details**:
    -   **Scene Name**: e.g., `FightScene`
    -   **Take Number**: e.g., `001`
    -   **Cameras**: e.g., `0, 1` (comma-separated).
3.  **Clap Sync**:
    -   Start Recording.
    -   **CLAP LOUDLY** once, visible to all cameras. This is crucial for audio sync.
4.  **Action**: Perform your motion.
5.  **Stop**: Click **STOP**.

### Step C: Processing & Import
1.  **Auto-Processing**:
    -   Upon stopping, the tool automatically:
        -   Stops the video subprocesses.
        -   Finds the audio "clap" spike.
        -   Runs OpenPose on the video files.
        -   Triangulates the 3D points.
        -   Exports a CSV file to `MocapExports/`.
2.  **Unreal Import**:
    -   If Unreal is open and the `mocap_watcher` is running, the CSV will be automatically imported.
    -   You will see a "Reimport" notification.
3.  **Playback**:
    -   Open your Level Sequence.
    -   Ensure your Control Rig is active.
    -   Scrub the timeline. The animation should play.

---

## 7. Troubleshooting

### "OpenPose binary not found"
-   Check the path in `src/processing/pipeline.py`.
-   Ensure OpenPose runs correctly from the command line first.

### "No sync spike found"
-   Ensure your microphone was active and the clap was distinct (loudest peak in the recording).
-   Check `src/capture/audio.py` logic.

### "Cameras fail to open"
-   Check if another app (Zoom, Teams, Discord) is using the webcam.
-   Check USB bandwidth limits.

### "Unreal doesn't import"
-   Check the Output Log in Unreal for "Python" messages.
-   Ensure `mocap_watcher` is running.
-   Verify the path `MocapImports` matches where the tool saves CSVs.

---

## 8. Developer Notes

-   **Architecture**: Modular design (Capture, Processing, GUI, OSC).
-   **Extensibility**:
    -   Add `calib_GUI.py` to graphical interface for calibration.
    -   Improve `filter.py` with specific IK constraints.
-   **License**: MIT License (assumed). OpenPose has its own non-commercial license (usually).

---
*Created by Virtual Production Engineer Agent*
