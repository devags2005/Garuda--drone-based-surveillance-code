document.addEventListener('DOMContentLoaded', function() {
    // DOM elements
    const form = document.getElementById('surveillance-form');
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const videoElement = document.getElementById('video');
    const statusIndicator = document.getElementById('status-indicator');
    const statusText = document.getElementById('status-text');
    const currentTimeElement = document.getElementById('current-time');
    const inputTypeRadios = document.querySelectorAll('input[name="input_type"]');
    const videoUploadDiv = document.getElementById('video-upload');
    
    // Update current time
    function updateCurrentTime() {
        const now = new Date();
        const timeString = now.toTimeString().split(' ')[0];
        currentTimeElement.textContent = timeString;
    }
    
    // Update time every second
    setInterval(updateCurrentTime, 1000);
    updateCurrentTime();
    
    // Toggle video upload field based on input type selection
    inputTypeRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            if (this.value === 'Video') {
                videoUploadDiv.style.display = 'block';
            } else {
                videoUploadDiv.style.display = 'none';
            }
        });
    });
    
    // Check surveillance status on page load
    checkStatus();
    
    // Start surveillance
    startBtn.addEventListener('click', function() {
        const formData = new FormData(form);
        
        // Validate form
        if (formData.get('input_type') === 'Video') {
            const fileInput = document.getElementById('video_file');
            if (!fileInput.files || fileInput.files.length === 0) {
                alert('Please upload a video file.');
                return;
            }
        }
        
        // Disable button to prevent multiple clicks
        startBtn.disabled = true;
        startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting...';
        
        // Start surveillance
        fetch('/start_surveillance', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                updateUIForRunning();
                // Start video stream with cache-busting parameter
                videoElement.src = '/video_feed?' + new Date().getTime();
            } else {
                alert('Failed to start surveillance: ' + data.message);
                startBtn.disabled = false;
                startBtn.innerHTML = '<i class="fas fa-play"></i> Start Surveillance';
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while starting surveillance.');
            startBtn.disabled = false;
            startBtn.innerHTML = '<i class="fas fa-play"></i> Start Surveillance';
        });
    });
    
    // Stop surveillance
    stopBtn.addEventListener('click', function() {
        // Disable button to prevent multiple clicks
        stopBtn.disabled = true;
        stopBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Stopping...';
        
        fetch('/stop_surveillance', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                updateUIForStopped();
            } else {
                alert('Failed to stop surveillance: ' + data.message);
                stopBtn.disabled = false;
                stopBtn.innerHTML = '<i class="fas fa-stop"></i> Stop Surveillance';
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while stopping surveillance.');
            stopBtn.disabled = false;
            stopBtn.innerHTML = '<i class="fas fa-stop"></i> Stop Surveillance';
        });
    });
    
    // Check surveillance status
    function checkStatus() {
        fetch('/status')
        .then(response => response.json())
        .then(data => {
            if (data.is_running) {
                updateUIForRunning();
                // Start video stream with cache-busting parameter
                videoElement.src = '/video_feed?' + new Date().getTime();
            } else {
                updateUIForStopped();
            }
        })
        .catch(error => {
            console.error('Error checking status:', error);
        });
    }
    
    // Update UI for running state
    function updateUIForRunning() {
        startBtn.disabled = true;
        startBtn.innerHTML = '<i class="fas fa-play"></i> Start Surveillance';
        stopBtn.disabled = false;
        stopBtn.innerHTML = '<i class="fas fa-stop"></i> Stop Surveillance';
        statusIndicator.classList.remove('offline');
        statusIndicator.classList.add('online');
        statusText.textContent = 'Online';
        
        // Disable form inputs
        Array.from(form.elements).forEach(element => {
            if (element !== stopBtn) {
                element.disabled = true;
            }
        });
    }
    
    // Update UI for stopped state
    function updateUIForStopped() {
        startBtn.disabled = false;
        startBtn.innerHTML = '<i class="fas fa-play"></i> Start Surveillance';
        stopBtn.disabled = true;
        stopBtn.innerHTML = '<i class="fas fa-stop"></i> Stop Surveillance';
        statusIndicator.classList.remove('online');
        statusIndicator.classList.add('offline');
        statusText.textContent = 'Offline';
        videoElement.src = '/static/img/placeholder.jpg?' + new Date().getTime();
        
        // Enable form inputs
        Array.from(form.elements).forEach(element => {
            if (element !== stopBtn) {
                element.disabled = false;
            }
        });
    }
});