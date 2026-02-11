
# Unreal Engine 5 Setup Guide for Mocap Tool

## 1. Prerequisites
- **Plugins**: Enable "OSC", "Python Editor Script Plugin", "Take Recorder", "Control Rig", "Live Link".
- **Project Settings**: 
  - Go to *Project Settings > Plugins > Python*.
  - Enable "Developer Mode" (for access to all Python API).
  - Add this folder (`.../mocap/unreal`) to your Python Import Paths.



---

## 2. Live Link Face (iPhone) Setup
1.  **Network**: Connect iPhone to the same Wi-Fi as your PC.
2.  **Target IP**: In the Live Link Face app settings, set **Targets > Add Target** to your **PC's Local IP Address** (e.g., `192.168.1.10`).
3.  **Operation**:
    -   The Python script sends a "Start Recording" trigger to the iPhone.
    -   The iPhone records locally and/or streams blendshapes directly to Unreal's Live Link subject.

---

## 3. BP_MocapOrchestrator Setup
Create a new Actor Blueprint named `BP_MocapOrchestrator` in your scene.


### OSC Listener
1. Add an **OSC Server** variable (Object Reference).
2. On `BeginPlay`:
   - Create OSC Server (Port 8000, IP 0.0.0.0).
   - Store reference.
   - Bind Event to On OSC Message Received.

### Message Logic
In the internal Event Graph:
1. **On OSC Message `/recStart`**:
   - `Take Recorder Blueprint Library` -> `Start Recording`.
   - Print String: "Recording Started via OSC".
2. **On OSC Message `/recStop`**:
   - `Take Recorder Blueprint Library` -> `Stop Recording`.
   - Print String: "Recording Stopped. Triggering Import...".
   - Execute Python Command: `import mocap_watcher; mocap_watcher.start_watching()` (or ensure watcher is running).

## 4. Mocap Watcher Script
To have the watcher run automatically:
1. Open *Project Settings > Plugins > Python*.
2. Add `mocap_watcher.py` to "Startup Scripts".
   - _Note: Use `import mocap_watcher; mocap_watcher.start_watching()` as the command if adding to startup commands, or just ensuring the module loads if it self-starts._
3. The script watches `[ProjectDir]/MocapImports` and imports found CSVs to `/Game/Mocap/DT_MocapLive`.

## 5. Control Rig Setup
Modify your MetaHuman or Character Control Rig.

### Data Table Reader
1. Create a variable `CurrentTime` (float).
2. Add a `Get Data Table Row` node.
   - Table: `DT_MocapLive`
   - Row Name: Convert `CurrentTime * FPS` to String (or Frame Number).
3. Break the Struct (`F_MocapData`).

### Driving Bones
1. For each bone (e.g., `pelvis`, `hand_l`, `head`):
   - Get the corresponding Vector from the broken struct.
   - Use `Set Global Transform` (or `Set Translation`) on the Control.
   - **Important**: Convert Coordinate Spaces!
     - OpenPose/Python: Y-Up or Z-Up? 
     - Unreal: Z-Up, Left-Handed.
     - You may need to swap Y/Z or invert X in the Rig logic.

### Ground Snap
1. Add variable `GroundOffset` (float).
2. Subtract this from the Pelvis Z height to snap character to floor.
