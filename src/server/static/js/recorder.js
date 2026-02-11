
let mediaRecorder;
let recordedChunks = [];
let audioContext;
let analyser;
let microphone;
let javascriptNode;
let socket;

const btnRec = document.getElementById('btnRec');
const btnStop = document.getElementById('btnStop');
const statusDiv = document.getElementById('status');
const preview = document.getElementById('preview');
const audioLevel = document.getElementById('audioLevel');

// Initialize SocketIO
function initSocket() {
  // Determine the socket URL based on current connection
  // socket.io.js is served automatically by flask-socketio
  socket = io();

  socket.on('connect', () => {
    console.log("Connected to Control Server");
    statusDiv.innerText = "Connected to Server";
  });

  socket.on('start_recording', (data) => {
    console.log("Received START command", data);
    document.getElementById('scene').value = data.scene;
    document.getElementById('take').value = data.take;
    startRecording();
  });

  socket.on('stop_recording', () => {
    console.log("Received STOP command");
    stopRecording();
  });

  socket.on('trigger_calibration', (data) => {
    console.log("Received CALIBRATION trigger", data);
    uploadCalibrationImage(data.count);
  });
}


function setupAudioMeter(stream) {
  audioContext = new (window.AudioContext || window.webkitAudioContext)();
  analyser = audioContext.createAnalyser();
  microphone = audioContext.createMediaStreamSource(stream);
  javascriptNode = audioContext.createScriptProcessor(2048, 1, 1);

  analyser.smoothingTimeConstant = 0.8;
  analyser.fftSize = 1024;

  microphone.connect(analyser);
  analyser.connect(javascriptNode);
  javascriptNode.connect(audioContext.destination);

  javascriptNode.onaudioprocess = function () {
    var array = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(array);
    var values = 0;
    var length = array.length;
    for (var i = 0; i < length; i++) {
      values += array[i];
    }
    var average = values / length;

    let percent = Math.min(100, average * 2);
    audioLevel.style.width = percent + "%";

    if (percent > 90) {
      audioLevel.classList.add("clip");
    } else {
      audioLevel.classList.remove("clip");
    }
  }
}

async function initCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
      audio: true
    });
    preview.srcObject = stream;
    setupAudioMeter(stream);

    let mimeType = 'video/webm;codecs=vp8,opus';
    if (!MediaRecorder.isTypeSupported(mimeType)) {
      mimeType = 'video/mp4';
    }
    statusDiv.innerText = `Ready (${mimeType})`;

    mediaRecorder = new MediaRecorder(stream, { mimeType: mimeType });

    mediaRecorder.ondataavailable = function (e) {
      if (e.data.size > 0) {
        recordedChunks.push(e.data);
      }
    };

    mediaRecorder.onstop = function () {
      uploadBlob();
    };

    // Initialize socket once camera is ready
    initSocket();

    // Start Preview Loop (10 FPS)
    setInterval(sendPreview, 100);


  } catch (err) {

    statusDiv.innerText = "Error: " + err;
    console.error(err);
  }
}

function startRecording() {
  if (mediaRecorder && mediaRecorder.state === "inactive") {
    recordedChunks = [];
    mediaRecorder.start();
    btnRec.disabled = true;
    btnStop.disabled = false;
    statusDiv.innerText = "Recording...";
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    btnRec.disabled = false;
    btnStop.disabled = true;
    statusDiv.innerText = "Processing...";
  }
}

function uploadBlob() {
  statusDiv.innerText = "Uploading...";
  const blob = new Blob(recordedChunks, { type: mediaRecorder.mimeType });
  recordedChunks = [];

  let formData = new FormData();
  formData.append("video", blob, "recording.webm");
  formData.append("timestamp", Date.now());
  formData.append("scene", document.getElementById('scene').value);
  formData.append("take", document.getElementById('take').value);
  formData.append("device_id", document.getElementById('deviceId').value);

  fetch('/upload_chunk', {
    method: 'POST',
    body: formData
  })
    .then(response => response.json())
    .then(data => {
      statusDiv.innerText = "Upload Complete!";
      console.log(data);
    })
    .catch(error => {
      statusDiv.innerText = "Upload Failed";
      console.error(error);
    });
}

function uploadCalibrationImage(count) {
  statusDiv.innerText = `Capturing Calib ${count}...`;

  // Capture from video stream to canvas
  const video = document.querySelector('video');
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

  canvas.toBlob(function (blob) {
    let formData = new FormData();
    formData.append("image", blob, `img_${count}.jpg`);
    formData.append("sid", socket.id);
    formData.append("count", count);

    fetch('/upload_calib', {
      method: 'POST',
      body: formData
    })
      .then(res => res.json())
      .then(data => {
        console.log("Calib upload success", data);
        statusDiv.innerText = `Calib ${count} Sent`;
      })
      .catch(err => {
        console.error("Calib upload failed", err);
        statusDiv.innerText = "Calib Failed";
      });
  }, 'image/jpeg', 0.95);
}


function sendPreview() {
  const video = document.querySelector('video');
  if (!video) return;

  // Check if socket connected
  if (!socket || !socket.connected) return;

  const canvas = document.createElement('canvas');
  // Low res for preview
  canvas.width = 320;
  canvas.height = 180;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

  canvas.toBlob(function (blob) {
    socket.emit('preview_frame', blob);
  }, 'image/jpeg', 0.5);
}

btnRec.onclick = startRecording;


btnRec.onclick = startRecording;

btnStop.onclick = stopRecording;

window.onload = initCamera;
