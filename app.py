from flask import Flask, render_template, Response, request, jsonify
from datetime import datetime
import pytz
import time
import cv2 as cv
from ultralytics import YOLO
import requests
import threading
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SECRET_KEY'] = 'garuda_surveillance_key'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Global variables to store settings
surveillance_settings = {
    'input_type': 'Camera',
    'source': 0,
    'token': '',
    'chat_id': '',
    'from_time': '00:00:00',
    'to_time': '23:59:59',
    'is_running': False,
    'playback_speed': 1.0,
    'target_fps': 15  # Added target FPS setting
}

# Function to check if the current time is within a specified range
def is_current_time_within_limits(from_time, to_time):
    try:
        current_time = datetime.now(pytz.timezone('Asia/Kolkata')).time()
        from_time_obj = datetime.strptime(from_time, '%H:%M:%S').time()
        to_time_obj = datetime.strptime(to_time, '%H:%M:%S').time()
        return from_time_obj <= current_time <= to_time_obj
    except ValueError:
        return False

# Improved VideoCapture class with better buffering and FPS control
class VideoCapture:
    def __init__(self, source, playback_speed=1.0, target_fps=15):
        self.cap = cv.VideoCapture(source)
        if not self.cap.isOpened():
            raise ValueError("Could not open video source")
            
        self.frame = None
        self.stopped = False
        self.lock = threading.Lock()
        self.new_frame_event = threading.Event()

        self.is_video_file = isinstance(source, str) and os.path.isfile(source)
        self.playback_speed = max(0.1, min(playback_speed, 10.0))  # Clamp between 0.1 and 10.0
        
        # Get video properties
        self.fps = self.cap.get(cv.CAP_PROP_FPS)
        if self.fps <= 0:
            self.fps = 30  # Default assumption if FPS cannot be determined
            
        self.frame_delay = 1.0 / (self.fps * self.playback_speed)
        self.target_fps = target_fps
        self.frame_skip = max(1, int(self.fps / self.target_fps)) if self.fps > target_fps else 1
        
        self.last_read_time = time.time()
        threading.Thread(target=self.update, daemon=True).start()

    def update(self):
        frame_count = 0
        while not self.stopped:
            ret, frame = self.cap.read()
            frame_count += 1
            
            if not ret:
                if self.is_video_file:
                    # Loop video file if we reach the end
                    self.cap.set(cv.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    time.sleep(0.1)  # For camera, wait and try again
                    continue
            
            # Skip frames if needed to match target FPS
            if frame_count % self.frame_skip != 0:
                continue
                
            with self.lock:
                self.frame = frame
                self.new_frame_event.set()
                
            # Control frame rate based on playback speed
            time.sleep(self.frame_delay)

    def read(self):
        self.new_frame_event.wait()  # Wait until a new frame is available
        with self.lock:
            self.new_frame_event.clear()
            if self.frame is None:
                return None
            return self.frame.copy()

    def get_fps(self):
        return min(self.fps, self.target_fps)  # Return effective FPS

    def stop(self):
        self.stopped = True
        self.cap.release()

# Function to add timestamp on image
def add_timestamp(img):
    current_time = datetime.now().strftime('%H:%M:%S')
    cv.putText(img, f"Time: {current_time}", (10, img.shape[0] - 10),
               cv.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    return img

# Function to send image to Telegram
def send_telegram_message(token, chat_id, img):
    try:
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        _, img_encoded = cv.imencode('.jpg', img)
        files = {'photo': ('image.jpg', img_encoded.tobytes(), 'image/jpeg')}
        data = {'chat_id': chat_id, 'caption': "Person detected!"}
        response = requests.post(url, data=data, files=files)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending message to Telegram: {e}")
        return False

# Video streaming generator function
def generate_frames():
    model = YOLO('yolov8n.pt')
    
    try:
        cap = VideoCapture(
            surveillance_settings['source'],
            surveillance_settings['playback_speed'],
            surveillance_settings['target_fps']
        )
    except Exception as e:
        print(f"Error initializing video capture: {e}")
        surveillance_settings['is_running'] = False
        return

    last_detection_time = time.time() - 10  # Initialize with offset
    frame_counter = 0
    
    while surveillance_settings['is_running']:
        if not is_current_time_within_limits(surveillance_settings['from_time'], surveillance_settings['to_time']):
            time.sleep(1)  # Longer sleep when outside time limits
            continue
            
        start_time = time.time()
        frame = cap.read()
        
        if frame is None:
            time.sleep(0.01)
            continue
        
        frame_counter += 1
        
        # Create a copy for processing to avoid modifying the original
        process_frame = frame.copy()
        
        # Resize frame for faster processing (maintaining aspect ratio)
        height, width = process_frame.shape[:2]
        new_width = 640
        new_height = int((new_width / width) * height)
        process_frame = cv.resize(process_frame, (new_width, new_height), interpolation=cv.INTER_LINEAR)
        
        # Perform object detection (every 3rd frame to reduce load)
        person_detected = False
        if frame_counter % 3 == 0:
            results = model.predict(process_frame, conf=0.4, verbose=False)
            
            # Process detection results
            for detection in results[0]:
                if int(detection.boxes.cls) == 0:  # Class 0: Person
                    person_detected = True
                    x1, y1, x2, y2 = map(int, detection.boxes.xyxy[0])
                    cv.rectangle(process_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv.putText(process_frame, "Person", (x1, y1 - 10),
                              cv.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        
        # Overlay timestamp
        process_frame = add_timestamp(process_frame)
        
        # Send frame to Telegram if a person is detected (with rate limiting)
        current_time = time.time()
        if (person_detected and 
            surveillance_settings['token'] and 
            surveillance_settings['chat_id'] and 
            (current_time - last_detection_time > 10)):
            last_detection_time = current_time
            # Use a thread to send the message asynchronously
            telegram_frame = process_frame.copy()
            threading.Thread(
                target=send_telegram_message,
                args=(surveillance_settings['token'], surveillance_settings['chat_id'], telegram_frame),
                daemon=True
            ).start()
        
        # Convert to JPEG for streaming
        ret, buffer = cv.imencode('.jpg', process_frame)
        frame_bytes = buffer.tobytes()
        
        yield (b'--frame\r\n'
              b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        # Calculate processing time and adjust if needed
        processing_time = time.time() - start_time
        target_time = 1.0 / surveillance_settings['target_fps']
        if processing_time < target_time:
            time.sleep(target_time - processing_time)
    
    cap.stop()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    if surveillance_settings['is_running']:
        return Response(generate_frames(),
                      mimetype='multipart/x-mixed-replace; boundary=frame')
    else:
        # Return a placeholder image when surveillance is not running
        with open('static/placeholder.jpg', 'rb') as f:
            placeholder = f.read()
        return Response(placeholder, mimetype='image/jpeg')

@app.route('/start_surveillance', methods=['POST'])
def start_surveillance():
    data = request.form
    
    surveillance_settings['input_type'] = data.get('input_type', 'Camera')
    surveillance_settings['token'] = data.get('token', '')
    surveillance_settings['chat_id'] = data.get('chat_id', '')
    surveillance_settings['from_time'] = data.get('from_time', '00:00:00')
    surveillance_settings['to_time'] = data.get('to_time', '23:59:59')
    
    # Get playback speed (clamped between 0.1 and 10.0)
    try:
        playback_speed = float(data.get('playback_speed', '1.0'))
        surveillance_settings['playback_speed'] = max(0.1, min(playback_speed, 10.0))
    except ValueError:
        surveillance_settings['playback_speed'] = 1.0
    
    # Get target FPS (clamped between 1 and 30)
    try:
        target_fps = float(data.get('target_fps', '15'))
        surveillance_settings['target_fps'] = max(1, min(target_fps, 30))
    except ValueError:
        surveillance_settings['target_fps'] = 15
    
    if surveillance_settings['input_type'] == 'Camera':
        surveillance_settings['source'] = 0
    else:
        # Handle uploaded video file
        if 'video_file' in request.files:
            file = request.files['video_file']
            if file.filename:
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                surveillance_settings['source'] = filepath
    
    surveillance_settings['is_running'] = True
    
    return jsonify({'status': 'success', 'message': 'Surveillance started'})

@app.route('/stop_surveillance', methods=['POST'])
def stop_surveillance():
    surveillance_settings['is_running'] = False
    return jsonify({'status': 'success', 'message': 'Surveillance stopped'})

@app.route('/status')
def status():
    return jsonify({
        'is_running': surveillance_settings['is_running'],
        'input_type': surveillance_settings['input_type'],
        'from_time': surveillance_settings['from_time'],
        'to_time': surveillance_settings['to_time'],
        'playback_speed': surveillance_settings['playback_speed'],
        'target_fps': surveillance_settings['target_fps']
    })

if __name__ == '__main__':
    app.run(debug=True, threaded=True)