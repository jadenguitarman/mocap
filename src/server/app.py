
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import os
import time

app = Flask(__name__)
# Allow CORS for local dev flexibiliy
socketio = SocketIO(app, cors_allowed_origins="*")

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_chunk', methods=['POST'])
def upload_chunk():
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

# --- REST Control API for Python GUI ---

@app.route('/api/start', methods=['POST'])
def api_start():
    data = request.json
    scene = data.get('scene', 'Scene')
    take = data.get('take', '001')
    
    print(f"[Server] Triggering START for {scene}_{take}")
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


@socketio.on('connect')
def test_connect():
    print('[Server] Client connected')

@socketio.on('disconnect')
def test_disconnect():
    print('[Server] Client disconnected')

if __name__ == '__main__':
    # Ad-hoc SSL context is required for getUserMedia on mobile
    # socketio.run wraps app.run
    socketio.run(app, host='0.0.0.0', port=5000, ssl_context='adhoc', debug=False, allow_unsafe_werkzeug=True)
