
# Unreal Engine 5 Setup Guide for Mocap Tool

## 1. Prerequisites
- **Plugins**: Enable "OSC", "Python Editor Script Plugin", "Take Recorder", "Control Rig", "Live Link".
- **Project Settings**: 
  - Go to *Project Settings > Plugins > Python*.
  - Enable "Developer Mode" (for access to all Python API).
  - Add this folder (`.../mocap/unreal`) to your Python Import Paths.
  - Add the path to the `mocap_watcher.py` file to the "Startup Scripts" section.


---

## 2. Live Link Face (iPhone) Setup
1.  **Network**: Connect iPhone to the same Wi-Fi as your PC.
2.  **Target IP**: In the Live Link Face app settings, click Live Link under the Streaming section, and set **Targets > Add Target** to your **PC's Local IP Address** (e.g., `192.168.0.101`).
3.  **Operation**:
    -   The Python script sends a "Start Recording" trigger to the iPhone.
    -   The iPhone records locally and/or streams blendshapes directly to Unreal's Live Link subject.

---

## 3. BP_MocapOrchestrator Setup
This Blueprint acts as the "Brain" in Unreal, listening for the Start/Stop commands from the Python app.

### 1. Create the Blueprint
1. In your **Content Browser**, Right-Click -> **Blueprint Class**.
2. Select **Actor** as the parent class.
3. Name it `BP_MocapOrchestrator` and open it.

### 2. Setup the OSC Listener
1. In the **My Blueprint** panel (bottom left), click the **+** button next to **Variables**.
2. Name the variable `OSCServer` and in the **Variable Type** dropdown, search for and select **OSC Server > Object Reference**.
3. Go to the **Event Graph**:
   - At **Event BeginPlay**, drag a wire and search for the **Create OSC Server** node.
   - Set **Receive IP Address** to `0.0.0.0`.
   - Set **Port** to `8000`.
   - Check the **Start Listening** checkbox.
   - Drag your `OSCServer` variable into the graph (select **Set**) and connect it to the output of **Create OSC Server**.
   - Drag a wire from your `OSCServer` variable and search for **Bind Event to On OSC Message Received**.
   - From the **Event** red pin, drag a wire and search for **Add Custom Event**. Name this event `OnOSCReceived`.

### 3. Implement the Start/Stop Logic
Now, we define what happens when a message arrives. In your `OnOSCReceived` event:
1. Drag a wire from the **Message** pin and search for **Get OSC Address**.
2. Drag from the **OSC Address** output and search for **Convert OSC Address to String**.
3. Drag from the String output and create a **Switch on String** node.
4. **Configure Pins in the Details Panel**:
   - Look at the **Details Panel** (usually on the right side of the screen) while the Switch on String node is selected.
   - Under the **Pin Names** section, click the **+ (Add Element)** button twice.
   - For **Index 0**, type: `/recStart`
   - For **Index 1**, type: `/recStop`
   - Notice that the pins on the actual node in the graph have now updated their names to match!
5. From the **`/recStart`** pin:
   - Search for the **Execute Console Command** node.
   - In the **Command** field, type: `RecordTake`
   - Add a **Print String** node that says "Mocap: Start Recording".
6. From the **`/recStop`** pin:
   - Search for the **Execute Console Command** node.
   - In the **Command** field, type: `StopRecording`
   - Add a **Print String** node that says "Mocap: Stop Recording. Importing...".
   - Drag a wire (after the Print String) to *another* **Execute Console Command** node.
   - In the **Command** field of this second node, enter: `py "import mocap_watcher; mocap_watcher.start_watching()"`
   - Leave the **Specific Player** pins empty on both nodes.

> **Pro Tip**: The `RecordTake` command will only work if you have already added at least one actor (like your MetaHuman) as a **Source** in the **Take Recorder window** (Window > Cinematics > Take Recorder).

### 4. Final Step
- **Compile and Save** the Blueprint.
- **Drag an instance** of `BP_MocapOrchestrator` from your Content Browser into your Level. It must be in the level to work!

## 4. Mocap Watcher & Auto-Import
To have the tool automatically send data to Unreal:
1. In the **Mocap Controller GUI**, the **Unreal Watch Path** field should be pointed to your Project's `MocapImports` folder.
   - **Tip**: You can set this permanently in your `config.toml` file under the `[Unreal]` section so you don't have to type it every time.
   - Example: `watch_path = "C:/Users/You/Documents/UnrealProjects/MyGame/MocapImports"`
2. When a take is finished processing, the tool will automatically copy the CSV to this folder.
3. To have Unreal import these found CSVs automatically, the **MOCAP WATCHER** must be running in Unreal. We added it to the startup scripts earlier, so it should start automatically when you open the project.
4. Found CSVs will be imported to `/Game/Mocap/DT_MocapLive`.

## 5. Driving a MetaHuman with Mocap Data
Follow these steps to apply the recorded CSV data to your MetaHuman.

### 1. Create the Control Rig
1. Find your MetaHuman's Control Rig (usually in `Content\MetaHumans\Common\Common\MetaHuman_ControlRig`).
2. **Duplicate it** and name the new one `CR_Mocap_MetaHuman`.
3. Open it and go to the **Rig Graph**.

### 2. Setup Variables
In the **My Blueprint** panel, create these variables:
- `MocapDataTable`: Type **Data Table > Object Reference**. 
  - *Default Value*: Select `DT_MocapLive`.
- `PlayTime`: Type **Float**.
- `FPS`: Type **Float** (Default: 30.0).

### 3. Reading the Mocap Row
In the Rig Graph (use the **Forwards Solve** event):
1. **Calculate Row Name**: 
   - Take `PlayTime`, multiply by `FPS`.
   - Use a **Map to Integer** node.
   - Use a **To String** node, then **Name** node.
2. **Get Data Table Row**:
   - Connection: `OSCServer` -> `Get Data Table Row`.
   - Row Name: Connect the name you just calculated.
3. **Break MocapData Struct**:
   - Drag from the **Out Row** pin and search for **Break F_MocapData**.
   - You will now see all 25 bones (Bone_0 to Bone_24).

### 4. Mapping to MetaHuman Controls
For each joint you want to drive (start with the Pelvis/Hip):
1. **Find the Control**: In the Rig Hierarchy, find `pelvis_ctrl` (or similar).
2. **Set Translation**:
   - Drag the control into the graph and select **Set Control Offset** (or **Set Translation**).
   - Connect the corresponding `Bone_X` vector from the Break Struct.
3. **Coordinate Conversion (CRITICAL)**:
   - Python/OpenPose uses a different coordinate system than Unreal.
   - For each bone vector, add a **Component to Vector** node.
   - **Swap Y and Z**: Connect the Struct's **Y** to Unreal's **Z**, and the Struct's **Z** to Unreal's **-Y**.
   - Scale: If your MetaHuman is too small/large, multiply the vector by a **Float (e.g., 100.0)**.

### 5. Bone Mapping Reference
The Tool exports 25 joints based on the OpenPose format. Map them like this:
- **Bone 0**: Pelvis / Root
- **Bone 1**: Spine Lower
- **Bone 2**: Right Shoulder
- **Bone 3**: Right Elbow
- **Bone 4**: Right Wrist
- **Bone 8**: Spine Mid / Neck Base
- **Bone 15-18**: Eyes/Face (can be ignored if using Live Link Face)

### 6. Apply to MetaHuman
1. Open your MetaHuman's **Blueprint**.
2. Select the **Body** component.
3. In the **Anim Class**, create a new **Anim Blueprint**.
4. In that AnimBP's **AnimGraph**:
   - Add a **Control Rig** node.
   - Select your `CR_Mocap_MetaHuman`.
   - Exposed Pins: Ensure `PlayTime` is exposed.
   - Connect `Current Time` from a sequence or a blueprint variable to the rig's `PlayTime`.
5. Connect to the **Output Pose**.
