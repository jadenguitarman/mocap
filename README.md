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

**All settings are located in `config.toml`.**

### Network Setup (OSC)
-   Edit `[Network]` section in `config.toml`.
-   **iphone_ip**: Set to your iPhone's IP address (Settings > Wi-Fi).
-   **unreal_ip**: Usually `127.0.0.1`.

### Camera Setup
-   Edit `[Camera]` section in `config.toml`.
-   **indices**: List of camera IDs, e.g., `[0, 1]`.

---

## 5. Calibration (Essential)

1.  **Capture**:
    Run the capture tool. It will snap synchronized photos from all cameras every 2 seconds.
    ```bash
    python src/calibrate_cli.py --capture
    ```
    *Tip: Move the ChArUco board around to cover different angles and depths.*

2.  **Process**:
    Run the calibration solver.
    ```bash
    python src/calibrate_cli.py --process
    ```
    This generates `calibration.npz`.

---

## 6. Unreal Engine Integration


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

## 7. Usage Workflow

### Step A: Recording
1.  **Launch the Controller**:
    ```bash
    python src/main.py
    ```
2.  **Check Settings**: Scene Name, Take Number, and Cameras are pre-loaded from config but can be edited.
3.  **Clap Sync**:
    -   Start Recording.
    -   **CLAP LOUDLY** once.
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
