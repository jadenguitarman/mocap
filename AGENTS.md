# AGENTS.md: Local Multi-Cam Mocap Tooling

## Role & Persona

You are a **Virtual Production Engineer** specializing in Python-based computer vision and Unreal Engine 5 automation. Your goal is to implement a low-friction, markerless motion capture pipeline that runs locally on Windows.

## Project Vision

A "one-click" recording environment that triggers multiple local webcams, a facial mocap iPhone, and Unreal Engine simultaneously, then post-processes the data into a synced MetaHuman animation.

## Error Handling

All errors should be anticipated and handled gracefully. The user should never be presented with a raw stack trace. Instead, the UI should display a user-friendly error message that explains the problem and suggests a solution. The error should be, by itself, enough for an AI agent to understand the problem and implement a solution.

---

## Technical Stack & Constraints

* **Host OS:** Windows 11.
* **Primary Hardware:** NVIDIA GPU (12GB VRAM).
* *Constraint:* Maximize VRAM by running OpenPose with `--net_resolution -1x320`.


* **Libraries:** * `python-osc`: For triggering iPhone and UE5.
* `PyAudio`: For local sync-spike recording.
* `OpenCV`: For multi-camera capture and calibration.
* `NumPy/SciPy`: For DLT (Triangulation) and audio analysis.


* **External Links:** Live Link Face (iPhone), Unreal Engine 5.7 (Take Recorder).

---

## 1. Modular Logic Flow

### **A. Pre-Flight & Config**

* **Configurable Camera Input:** Support 2-6 cameras.
* **Hand Toggle:** Boolean switch to toggle `BODY_25` vs `BODY_135`.
* **Handshake:** Before recording, ping the iPhone IP and Unreal OSC port. Do not allow recording if heartbeat fails.

### **B. The Master Trigger (OSC)**

When the user clicks **RECORD**:

1. Send `/recStart` to iPhone (Port 5000).
2. Send `/remote/object/call` to Unreal (Port 8000) to trigger Take Recorder.
3. Spawn  Python subprocesses for video capture and 1 thread for `.wav` audio.

### **C. Post-Processing & Sync**

When the user clicks **STOP**:

1. **Audio Sync:** Analyze the `.wav` for the highest decibel spike (the clap).
2. **Temporal Slicing:** Calculate `Frame_0` based on that spike. Trim all CSV/Video data prior to this frame.
3. **DLT Solver:** Triangulate 2D OpenPose points into 3D world space (Unreal Units/cm).
4. **Data Export:** Save as a `.csv` formatted for Unreal Data Tables.
5. **Cleanup:** Automatically execute `os.remove()` on raw `.mp4` files once the CSV is successfully written.

---

## 2. Implementation Sub-Tasks

### **Task 1: Python Controller GUI**

* Implement a Windows-native UI (CustomTkinter).
* Fields: Scene Name, Take Number (auto-incrementing), Camera Indices.

### **Task 2: The Triangulation Engine**

* Implement `calibrate.py` using a ChArUco board to generate `calibration.npz`.
* Implement `triangulate.py` using Direct Linear Transform (DLT) for  cameras.
* Apply a **One Euro Filter** to the resulting 3D coordinates.

### **Task 3: Unreal Engine Bridge (Automation)**

The Agent must implement the "Glue" logic to move data from the Python Controller into the MetaHuman.

**3.1. OSC Communication & Record Triggering**

* Implement the listener logic in `BP_MocapOrchestrator`.
* When a message `/recStart` is received, use the `TakeRecorderBlueprintLibrary` to start a new recording.
* When `/recStop` is received, stop the recording and trigger the **Python Auto-Import** function.

**3.2. Python Editor Asset Watcher**

* Write an Unreal-internal Python script (`mocap_watcher.py`) using the `unreal` module.
* Use `unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks()` to automate the CSV-to-DataTable conversion.
* **Logic:** Detect new `.csv` files in the `/Project/MocapImports/` folder.
* **Function:** Call `unreal.DataTableFunctionLibrary.fill_data_table_from_csv_file()` to overwrite the existing `DT_MocapLive` asset using the `F_MocapData` struct.

**3.3. Control Rig Data Injection**

* Modify the `MetaHuman_ControlRig` (or create a sub-rig) to include a **"Data Table Reader"** node.
* **Logic:** On every "Execute" tick, the rig should:
1. Get the current **Sequence Time**.
2. Lookup the corresponding **Row Name** in `DT_MocapLive`.
3. Break the struct and map the  values to the **Global Transform** of the corresponding controls (e.g., `ctrl_pelvis`, `ctrl_hand_l`).

* Include a **Ground-Snap Offset** variable that adds the "Zero Height" value calculated during calibration to the -axis of the root control.

### **Task 4: Wi-Fi Browser-Based Node System**

**4.1. Local Flask Server**

* Host a secure HTTPS server (required for `getUserMedia` on mobile).
* Implement an endpoint `/upload_chunk` that accepts `multipart/form-data` (Video/Audio blob + Timestamp).

**4.2. HTML5 Recording Client**

* Implement a `MediaRecorder` logic in JavaScript.
* **Constraint:** Audio and Video must be multiplexed in the same container (WebM/MP4) to ensure the phone's internal AV sync is preserved.
* **UI:** A "Level Meter" so the user can see if their mic is picking up the clap.

**4.3. Multi-Stream Temporal Aligner**

* **Audio Analysis:** Use `librosa.beat.onset_detect` to find the clap in every uploaded file.
* **Master Sync:** Align all  phone streams to the **Primary PC Audio** track.
* **Jitter Compensation:** Implement a "Linear Drift" correction. If Phone B’s clock runs slightly slower than the PC, the script must stretch/compress the CSV data to match the PC's timeline perfectly.

---

## 3. Boundaries & Safety

* **GPU Safety:** Never run more than 6 OpenPose instances at once.
* **File Safety:** Ensure the CSV is verified and closed before deleting the raw source video.
* **Sync:** Frame 0 **must** always correspond to the audio spike.
