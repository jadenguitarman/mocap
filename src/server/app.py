
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
