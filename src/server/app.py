
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
import os
import time
import io


app = Flask(__name__)
# Allow CORS for local dev flexibiliy
socketio = SocketIO(app, cors_allowed_origins="*")

connected_devices = {} # sid -> info
latest_previews = {} # sid -> jpeg_bytes


UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

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
        device_id = request.form.get('device_id', 'unknown')

        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        filename = f"{scene}_{take}_{device_id}_{timestamp}.webm"
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(save_path)
        
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
    target_devices = data.get('devices', None) # List of SIDs
    
    print(f"[Server] Triggering START for {scene}_{take}")
    
    if target_devices is not None:
        count = 0
        for sid in target_devices:
            # Check if sid is connected
            if sid in connected_devices:
                socketio.emit('start_recording', {'scene': scene, 'take': take}, to=sid)
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
        
        sid = request.form.get('sid', 'unknown')
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


    print(f"[Server] Saved calibration image from {sid}: {filename}")
    return jsonify({'status': 'uploaded'})

@app.route('/api/devices', methods=['GET'])
def api_devices():
    return jsonify(list(connected_devices.values()))

@app.route('/api/preview/<sid>')
def api_preview(sid):
    if sid in latest_previews:
        return send_file(io.BytesIO(latest_previews[sid]), mimetype='image/jpeg')
    return "", 404

@socketio.on('preview_frame')
def handle_preview(data):
    # data is binary/bytes of jpeg
    latest_previews[request.sid] = data

@socketio.on('connect')
def test_connect():
    print(f'[Server] Client connected: {request.sid}')
    connected_devices[request.sid] = {'sid': request.sid, 'type': 'mobile', 'address': request.remote_addr}

@socketio.on('disconnect')
def test_disconnect():
    print(f'[Server] Client disconnected: {request.sid}')
    connected_devices.pop(request.sid, None)
    latest_previews.pop(request.sid, None)



if __name__ == '__main__':
    # Ad-hoc SSL context is required for getUserMedia on mobile
    # socketio.run wraps app.run
    socketio.run(app, host='0.0.0.0', port=5000, ssl_context='adhoc', debug=False, allow_unsafe_werkzeug=True)
