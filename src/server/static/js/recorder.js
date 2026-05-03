
let mediaRecorder;
let recordedChunks = [];
let audioContext;
let analyser;
let microphone;
let javascriptNode;
let socket;
let persistentDeviceId;
let recordStartMs = null;
let recordStopMs = null;

const btnRec = document.getElementById('btnRec');
const btnStop = document.getElementById('btnStop');
const statusDiv = document.getElementById('status');
const preview = document.getElementById('preview');
const audioLevel = document.getElementById('audioLevel');

function getPersistentDeviceId() {
  const key = 'mocapDeviceId';
  let value = localStorage.getItem(key);
  if (!value) {
    const randomPart = crypto && crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
    value = `phone-${randomPart}`;
    localStorage.setItem(key, value);
  }
  return value;
}

// Initialize SocketIO
function initSocket() {
  // Determine the socket URL based on current connection
  // socket.io.js is served automatically by flask-socketio
  socket = io();

  socket.on('connect', () => {
    console.log("Connected to Control Server");
    statusDiv.innerText = "Connected to Server";
    persistentDeviceId = getPersistentDeviceId();
    document.getElementById('deviceId').value = persistentDeviceId;
    socket.emit('register_device', { device_id: persistentDeviceId });
  });

  socket.on('device_registered', (data) => {
    persistentDeviceId = data.device_id;
    document.getElementById('deviceId').value = persistentDeviceId;
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
  if (stream.getAudioTracks().length === 0) {
    console.warn("No audio tracks available for metering.");
    audioLevel.style.width = "0%";
    return;
  }

  try {
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
  } catch (e) {
    console.error("Audio Meter setup failed:", e);
  }
}

async function initCamera() {
  if (!window.isSecureContext) {
    const httpsUrl = window.location.href.replace(/^http:/, 'https:');
    statusDiv.style.color = "#ff6b6b";
    statusDiv.innerHTML = `Camera blocked: this page is open over HTTP.<br><br>Open <strong>${httpsUrl}</strong>, accept the certificate warning, then tap ENABLE CAMERA & JOIN again.`;
    console.warn("Camera blocked because page is not a secure context.");
    return;
  }

  // Try to go fullscreen on user gesture
  try {
    const docElm = document.documentElement;
    if (docElm.requestFullscreen) {
      docElm.requestFullscreen();
    } else if (docElm.mozRequestFullScreen) {
      docElm.mozRequestFullScreen();
    } else if (docElm.webkitRequestFullScreen) {
      docElm.webkitRequestFullScreen();
    } else if (docElm.msRequestFullscreen) {
      docElm.msRequestFullscreen();
    }
  } catch (e) {
    console.warn("Fullscreen request failed", e);
  }

  statusDiv.innerText = "Initializing...";

  // Hide the start button once we begin
  if (startCameraBtn) startCameraBtn.style.display = 'none';

  try {
    const tryConstraints = [
      {
        video: {
          facingMode: { exact: "environment" },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
          frameRate: { ideal: 30 },
          focusMode: "continuous"
        },
        audio: true
      },
      {
        video: {
          facingMode: "environment",
          width: { ideal: 1920 },
          height: { ideal: 1080 },
          frameRate: { ideal: 30 },
          focusMode: "continuous"
        },
        audio: true
      },
      { video: true, audio: true }
    ];

    // Disable modification of control fields
    document.getElementById('scene').readOnly = true;
    document.getElementById('take').readOnly = true;
    document.getElementById('deviceId').readOnly = true;

    if (!navigator.mediaDevices) {
      statusDiv.style.color = "#ff6b6b";
      let errorMsg = "<strong>Camera Error:</strong> Browser security blocked the camera.<br><br>";
      errorMsg += "Chrome only allows cameras on HTTPS or 'Secure' sites.<br><br>";
      errorMsg += "<strong>To fix:</strong><br>";
      errorMsg += "1. Open Chrome and go to: <code>chrome://flags/#unsafely-treat-insecure-origin-as-secure</code><br>";
      errorMsg += `2. Add <code>${window.location.origin}</code> to the list.<br>`;
      errorMsg += "3. Set to 'Enabled' and <strong>Relaunch Chrome</strong>.";
      statusDiv.innerHTML = errorMsg;
      throw new Error("navigator.mediaDevices is undefined (Insecure Context)");
    }

    let stream = null;
    let lastErr = null;

    for (const constraints of tryConstraints) {
      try {
        console.log("Attempting getUserMedia with:", constraints);
        stream = await navigator.mediaDevices.getUserMedia(constraints);
        if (stream) break;
      } catch (e) {
        console.warn(`Failed constraints:`, constraints, e);
        lastErr = e;
      }
    }

    if (!stream) {
      statusDiv.style.color = "#ff6b6b";
      statusDiv.innerHTML = "Camera Denied. Tap the 'Lock' icon in the address bar and reset permissions.";
      throw lastErr;
    }

    preview.srcObject = stream;
    await configureVideoTrack(stream);
    setupAudioMeter(stream);

    let mimeType = 'video/webm;codecs=vp8,opus';
    if (!MediaRecorder.isTypeSupported(mimeType)) {
      mimeType = 'video/mp4';
    }
    statusDiv.innerText = `Ready (${mimeType})`;
    statusDiv.style.color = "";

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
    if (!socket) {
      initSocket();
    }

    // Start Preview Loop (10 FPS)
    setInterval(sendPreview, 100);

    // Hide start button
    const startBtn = document.getElementById('btnStartCamera');
    if (startBtn) startBtn.style.display = 'none';

  } catch (err) {
    statusDiv.style.color = "#ff6b6b";
    statusDiv.innerText = "Camera Error: " + err.name + " - " + err.message;
    console.error("Camera init failed:", err);

    if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
      statusDiv.innerText += "\n\nPermission was denied. Chrome may block the camera if the certificate is not trusted. \nTry selecting 'Advanced' -> 'Proceed' on the warning page, or use a desktop browser.";
    }
  }
}

async function configureVideoTrack(stream) {
  const track = stream.getVideoTracks()[0];
  if (!track || !track.applyConstraints) return;

  try {
    const caps = track.getCapabilities ? track.getCapabilities() : {};
    const advanced = [];
    if (caps.focusMode && caps.focusMode.includes("continuous")) {
      advanced.push({ focusMode: "continuous" });
    }
    if (caps.exposureMode && caps.exposureMode.includes("continuous")) {
      advanced.push({ exposureMode: "continuous" });
    }
    if (caps.whiteBalanceMode && caps.whiteBalanceMode.includes("continuous")) {
      advanced.push({ whiteBalanceMode: "continuous" });
    }
    if (advanced.length > 0) {
      await track.applyConstraints({ advanced });
    }
  } catch (e) {
    console.warn("Camera focus/exposure tuning not supported:", e);
  }
}

function startRecording() {
  if (mediaRecorder && mediaRecorder.state === "inactive") {
    recordedChunks = [];
    recordStartMs = performance.now();
    recordStopMs = null;
    mediaRecorder.start();
    btnRec.disabled = true;
    btnStop.disabled = false;
    statusDiv.innerText = "Recording...";
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    recordStopMs = performance.now();
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
  formData.append("sync_start", recordStartMs === null ? "" : String(recordStartMs / 1000));
  formData.append("sync_end", recordStopMs === null ? "" : String(recordStopMs / 1000));

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

  const video = document.querySelector('video');
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

  canvas.toBlob(function (blob) {
    let formData = new FormData();
    formData.append("image", blob, `img_${count}.jpg`);
    formData.append("device_id", document.getElementById('deviceId').value);
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
  if (!video || !video.videoWidth) return;

  if (!socket || !socket.connected) return;

  const canvas = document.createElement('canvas');
  canvas.width = 320;
  canvas.height = 180;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

  canvas.toBlob(function (blob) {
    socket.emit('preview_frame', blob);
  }, 'image/jpeg', 0.5);
}

btnRec.onclick = startRecording;
btnStop.onclick = stopRecording;

// Use a button for user gesture
const startCameraBtn = document.createElement('button');
startCameraBtn.id = 'btnStartCamera';
startCameraBtn.innerText = 'ENABLE CAMERA & JOIN';
startCameraBtn.style.background = '#2ecc71';
startCameraBtn.style.color = 'white';
startCameraBtn.style.padding = '20px';
startCameraBtn.style.fontSize = '20px';
startCameraBtn.style.margin = '20px';
startCameraBtn.style.borderRadius = '10px';
startCameraBtn.style.border = 'none';
startCameraBtn.style.cursor = 'pointer';
startCameraBtn.style.fontWeight = 'bold';
startCameraBtn.onclick = initCamera;

window.onload = () => {
  const status = document.getElementById('status');
  status.parentNode.insertBefore(startCameraBtn, status);
};
