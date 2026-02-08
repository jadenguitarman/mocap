
import unreal
import os
import time
import threading

# Config
WATCH_DIR = os.path.join(unreal.Paths.project_dir(), "MocapImports")
DEST_PATH = "/Game/Mocap/DT_MocapLive"
STRUCT_PATH = "/Game/Mocap/F_MocapData.F_MocapData" 

def watch_loop():
    print(f"[MocapWatcher] Watching {WATCH_DIR} for new CSVs...")
    
    seen_files = set()
    if os.path.exists(WATCH_DIR):
        seen_files = set(os.listdir(WATCH_DIR))
    
    while True:
        if not os.path.exists(WATCH_DIR):
            os.makedirs(WATCH_DIR)
            
        current_files = set(os.listdir(WATCH_DIR))
        new_files = current_files - seen_files
        
        for f in new_files:
            if f.endswith(".csv"):
                full_path = os.path.join(WATCH_DIR, f)
                # Wait for write to finish? 
                # Simple check: try to open
                try_import(full_path)
                
        seen_files = current_files
        time.sleep(1.0)

def try_import(csv_path):
    print(f"[MocapWatcher] Found new file: {csv_path}")
    
    # Wait a bit for file lock release
    time.sleep(0.5)
    
    # Import Task
    task = unreal.AssetImportTask()
    task.filename = csv_path
    task.destination_path = os.path.dirname(DEST_PATH)
    task.destination_name = os.path.basename(DEST_PATH)
    task.replace_existing = True
    task.automated = True
    task.save = True

    # CSV Factory Settings
    factory = unreal.CSVImportFactory()
    factory.automated_import_settings.import_row_struct = unreal.load_asset(STRUCT_PATH)
    factory.automated_import_settings.import_type = unreal.CSVImportType.ECSV_DT_DATA_TABLE
    
    task.factory = factory
    
    # Execute
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    print(f"[MocapWatcher] Imported to {DEST_PATH}")

# Start background thread
# Note: Unreal Python threading can be tricky. 
# Usually we hook into Editor Tick or use a timer.
# For simplicity here, we'll just run it or provide the class.
# In a real plugin, we'd use unreal.register_slate_post_tick_callback

# To run manually:
# import mocap_watcher
# mocap_watcher.start_watching()

stop_event = threading.Event()

def start_watching():
    global stop_event
    stop_event.clear()
    t = threading.Thread(target=watch_loop)
    t.start()

def stop_watching():
    global stop_event
    stop_event.set()
