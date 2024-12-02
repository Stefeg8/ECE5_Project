import socket
import sounddevice as sd
import numpy as np
import cv2
import threading
from ultralytics import YOLO
import queue
import serial
import time

# config
SERVER_IP = '169.231.9.9'  
SERVER_PORT = 42069 
BUFFER_SIZE = 1024  #packet size

# Video config
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
VIDEO_BUFFER_SIZE = 4096
VIDEO_FPS = 20 

FS = 16000  # Sampling rate
CHANNELS = 1  # Mono
DURATION = 0.1  # Duration of each audio packet capture

model = YOLO("/path/to/yolov10n.pt")  # Update with the correct path
class_names_list = None
with open('/path/to/coco.names', 'r') as f:  # Update with the correct path
    class_names_list = [line.strip() for line in f.readlines()]

arduino = serial.Serial('/dev/ttyUSB0', 9600)  # erm wtf
time.sleep(2) 

def dir_movement(x, y):
    """Handles actions when follow mode is active."""
    print(f"Performing follow action with coordinates: x={x}, y={y}")
    
    # Decide movement based on x and y
    if x > 0 and y > 0:
        command = 'F'  # Forward
    elif x < 0 and y > 0:
        command = 'L'  # Left
    elif x > 0 and y < 0:
        command = 'R'  # Right
    elif x < 0 and y < 0:
        command = 'B'  # Backward
    else:
        command = 'S'  # Stop
    
    # Send command to Arduino
    arduino.write(command.encode())
    print(f"Sent command to Arduino: {command}")

def directions(x, y, client_socket):
    """Processes the detected coordinates and communicates with the server."""
    try:
        # Send the CHECK_FOLLOW message to the server
        message = f"CHECK_FOLLOW {x} {y}"
        client_socket.sendall(message.encode())
        print(f"Sent directions to server: {message}")
        
        # Wait for and process the follow status from the server
        data = client_socket.recv(1024).decode()
        if "follow:true" in data:
            print("Server confirmed: Follow mode active.")
            dir_movement(x, y)  # Call a function if follow is active
        elif "follow:false" in data:
            print("Server confirmed: Follow mode inactive.")
    except Exception as e:
        print(f"Error in directions function: {e}")

def record_and_send_audio(client_socket):
    """Records audio in chunks and sends it to the server in real time."""
    try:
        # Continuously record and send audio
        print("Starting audio streaming...")
        while True:
            # Record a small chunk of audio
            audio_chunk = sd.rec(
                int(DURATION * FS), 
                samplerate=FS, 
                channels=CHANNELS, 
                dtype='int16'
            )
            sd.wait()  # W]ait until the audio is fully recorded
            
            # Convert audio data to bytes
            audio_bytes = audio_chunk.tobytes()
            
            # Send audio data in chunks of BUFFER_SIZE
            for i in range(0, len(audio_bytes), BUFFER_SIZE):
                packet = audio_bytes[i:i + BUFFER_SIZE]
                client_socket.sendall(packet)
            receive_and_play_audio(client_socket)
    
    except KeyboardInterrupt:
        print("\nStreaming stopped.")
    except Exception as e:
        print(f"An error occurred: {e}")
def receive_and_play_audio(client_socket):
    """Receives audio data from the server and plays it in real time."""
    audio_buffer = bytearray()  # Buffer to accumulate audio data
    
    try:
        # Continuously receive audio data from the server
        while True:
            data = client_socket.recv(BUFFER_SIZE)
            if not data:
                break  # If no data is received, exit the loop
            
            # Append the received data to the buffer
            audio_buffer.extend(data)

            # If the buffer has enough data for a playback chunk
            if len(audio_buffer) >= FS * 2 * CHANNELS:
                # Convert the buffer into a NumPy array for playback
                audio_data = np.frombuffer(audio_buffer[:FS * 2 * CHANNELS], dtype=np.int16)
                
                # Play the audio data
                sd.play(audio_data, samplerate=FS)
                sd.wait()  # Wait until playback is complete
                
                # Remove the played portion from the buffer
                audio_buffer = audio_buffer[FS * 2 * CHANNELS:]
    
    except Exception as e:
        print(f"Error during audio playback: {e}")
        
def capture_and_send_video(client_socket):
    """Captures video frames, processes them, and sends them to the server."""
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, VIDEO_FPS)

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            # YOLO Object Detection
            results = model(frame)[0]
            for result in results.boxes.data:
                x_min, y_min, x_max, y_max, confidence, class_id = result.tolist()
                if int(class_id) < len(class_names_list) and class_names_list[int(class_id)] == "person":
                    center_x = (x_min + x_max) / 2
                    center_y = (y_min + y_max) / 2
                    directions(center_x, center_y)

    except Exception as e:
        print(f"Video streaming error: {e}")
    finally:
        cap.release()

def main():
    """Main function to start threads for audio and video streaming."""
    print(f"Connecting to server at {SERVER_IP}:{SERVER_PORT}...")
    
    # Connect to server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
        client_socket.connect((SERVER_IP, SERVER_PORT))
        print("Connected to server.")
        
        # Create and start threads
        audio_thread = threading.Thread(target=record_and_send_audio, args=(client_socket,))
        video_thread = threading.Thread(target=capture_and_send_video, args=(client_socket,))
        audio_thread.start()
        video_thread.start()

        # Wait for threads to complete
        audio_thread.join()
        video_thread.join()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Failed to start: {e}")
