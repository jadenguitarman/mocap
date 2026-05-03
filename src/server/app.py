
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
import os
import time
import io
try:
    from identity import register_device as register_device_state
    from identity import sanitize_token
except ImportError:
    from server.identity import register_device as register_device_state
    from server.identity import sanitize_token


app = Flask(__name__)

# Suppress flask/werkzeug access logs to keep terminal clean
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Allow CORS for local dev flexibiliy
socketio = SocketIO(app, cors_allowed_origins="*")

connected_devices = {} # device_id -> info
sid_to_device = {} # socket sid -> persistent device_id
latest_previews = {} # device_id -> jpeg_bytes


UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def register_device(socket_sid, device_id, address):
    return register_device_state(connected_devices, sid_to_device, latest_previews, socket_sid, device_id, address)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_chunk', methods=['POST'])
def upload_chunk():
    try:
        if 'video' not in request.files:
            return jsonify({'error': 'No video part'}), 400
        
        file = request.files['video']
        timestamp = request.form.get('timestamp')
        scene = request.form.get('scene', 'test')
        take = request.form.get('take', '001')
        if not request.form.get('device_id'):
            return jsonify({'error': 'Missing persistent device_id. Reload the mobile recorder page and join again.'}), 400
        device_id = sanitize_token(request.form.get('device_id'))
        sync_start = request.form.get('sync_start', '')
        sync_end = request.form.get('sync_end', '')

        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        filename = f"{scene}_{take}_{device_id}_{timestamp}.webm"
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(save_path)

        meta_path = os.path.splitext(save_path)[0] + ".json"
        with open(meta_path, "w") as meta_file:
            import json
            json.dump({
                "device_id": device_id,
                "scene": scene,
                "take": take,
                "timestamp": timestamp,
                "sync_start": sync_start,
                "sync_end": sync_end,
            }, meta_file, indent=2)
        
        print(f"[Server] Received chunk from {device_id}: {filename}")
        return jsonify({'message': 'Upload successful', 'path': save_path}), 200
    except Exception as e:
        print(f"[Server] Error in /upload_chunk: {e}")
        return jsonify({'error': str(e)}), 500


# --- REST Control API for Python GUI ---

@app.route('/api/start', methods=['POST'])
def api_start():
    data = request.json
    scene = data.get('scene', 'Scene')
    take = data.get('take', '001')
    target_devices = data.get('devices', None) # List of persistent device ids
    
    print(f"[Server] Triggering START for {scene}_{take}")
    
    if target_devices is not None:
        count = 0
        for device_id in target_devices:
            device = connected_devices.get(device_id)
            if device:
                socketio.emit('start_recording', {'scene': scene, 'take': take}, to=device['sid'])
                count += 1
        print(f"[Server] Started {count} mobile devices.")
    else:
        # Broadcast
        socketio.emit('start_recording', {'scene': scene, 'take': take})
        
    return jsonify({'status': 'started', 'scene': scene, 'take': take})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    print(f"[Server] Triggering STOP")
    socketio.emit('stop_recording', {})
    return jsonify({'status': 'stopped'})

@app.route('/api/trigger_calibration', methods=['POST'])
def api_trigger_calibration():
    data = request.json
    count = data.get('count', 0)
    print(f"[Server] Triggering CALIBRATION capture {count}")
    socketio.emit('trigger_calibration', {'count': count})
    return jsonify({'status': 'triggered', 'count': count})

@app.route('/upload_calib', methods=['POST'])
def upload_calib():
    try:
        if 'video' not in request.files: # Reusing blobl logic, but for image?
             # Check if it's an image or video blob
             if 'image' in request.files:
                 file = request.files['image']
             else:
                 file = request.files['video']
        else:
            file = request.files['video']

        # Logic: client sends blob, we save it.
        # We need a unique ID for the phone (SID?).
        # Helper: we can get SID from headers or args if client sends it.
        # Client JS: formData.append('sid', socket.id)
        
        if not request.form.get('device_id'):
            return jsonify({'error': 'Missing persistent device_id. Reload the mobile recorder page and join again.'}), 400
        sid = sanitize_token(request.form.get('device_id'))
        count = request.form.get('count', '0')
        
        # Dir: calibration_images/mobile_{sid}
        save_dir = os.path.join("calibration_images", f"mobile_{sid}")
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
            
        filename = f"img_{int(count):04d}.jpg" # Client should send JPG blob
        
        file.save(os.path.join(save_dir, filename))
        print(f"[Server] Saved calibration image from {sid}: {filename}")
        return jsonify({'status': 'uploaded'})
    except Exception as e:
        print(f"[Server] Error in /upload_calib: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/devices', methods=['GET'])
def api_devices():
    return jsonify(list(connected_devices.values()))

@app.route('/api/preview/<device_id>')
def api_preview(device_id):
    device_id = sanitize_token(device_id)
    if device_id in latest_previews:
        return send_file(io.BytesIO(latest_previews[device_id]), mimetype='image/jpeg')
    return "", 404

@socketio.on('preview_frame')
def handle_preview(data):
    device_id = sid_to_device.get(request.sid)
    if device_id:
        latest_previews[device_id] = data

@socketio.on('register_device')
def handle_register_device(data):
    device_id = sanitize_token((data or {}).get('device_id'), request.sid)
    device = register_device(request.sid, device_id, request.remote_addr)
    emit('device_registered', {'device_id': device['id']})

@socketio.on('connect')
def test_connect():
    print(f'[Server] Client connected: {request.sid}')

@socketio.on('disconnect')
def test_disconnect():
    print(f'[Server] Client disconnected: {request.sid}')
    device_id = sid_to_device.pop(request.sid, None)
    if device_id:
        connected_devices.pop(device_id, None)
        latest_previews.pop(device_id, None)




if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-ssl", action="store_true", help="Run without SSL (useful for Chrome Flag workaround)")
    args = parser.parse_args()

    ssl_setting = 'adhoc'
    if args.no_ssl:
        print("[Server] RUNNING IN HTTP MODE (No SSL). Use Chrome Flags to enable camera.")
        ssl_setting = None

    # Ad-hoc SSL context is required for getUserMedia on mobile
    # socketio.run wraps app.run
    socketio.run(app, host='0.0.0.0', port=5000, ssl_context=ssl_setting, debug=False, allow_unsafe_werkzeug=True)
