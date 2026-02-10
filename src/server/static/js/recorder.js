
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

btnRec.onclick = startRecording;
btnStop.onclick = stopRecording;

window.onload = initCamera;
