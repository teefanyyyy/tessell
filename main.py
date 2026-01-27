import serial
import serial.tools.list_ports
import time
import os
import wave
import difflib
import json
import sys
import speech_recognition as sr
from vosk import Model, KaldiRecognizer
import tkinter as tk
from tkinter import filedialog, scrolledtext
import threading
import socket

BAUD = 921600                
TEMP_WAV = "temp_audio.wav"
MAX_GOOGLE_LATENCY = 2.0

# theme
THEME = {
    "bg_main": "#fdd9dd",
    "bg_header": "#ffc2cd",
    "bg_log": "#fff0f5",
    "text_main": "#4a2c35",
    "text_light": "#755c62",
    "accent_blue": "#5d7cba",
    "accent_green": "#4e8c64",
    "accent_red": "#c94c4c",
}

# exe
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# gui
class VoiceFileFinderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("tessell")
        self.root.geometry("800x600")
        self.root.resizable(False, False)
        self.root.configure(bg=THEME["bg_main"])
        
        self.search_path = None
        self.ser = None
        self.running = False
        self.popup_window = None
        self.components_ready = False
        self.vosk_model = None
        self.google_recognizer = None
        self.use_google = True 
        
        header_frame = tk.Frame(root, bg=THEME["bg_header"], height=140)
        header_frame.pack(fill=tk.X, side=tk.TOP)
        header_frame.pack_propagate(False) # Prevents shrinking
        
        title = tk.Label(header_frame, text="tessell", 
                        font=("Segoe UI", 28, "bold"), fg=THEME["text_main"], bg=THEME["bg_header"])
        title.pack(pady=(15, 5))
        
        status_container = tk.Frame(header_frame, bg=THEME["bg_header"])
        status_container.pack(fill=tk.X, pady=5)
        
        self.status_label = tk.Label(status_container, text="⚙️ INITIALIZING", 
                                     font=("Segoe UI", 16, "bold"), fg=THEME["text_main"], bg=THEME["bg_header"])
        self.status_label.pack()
        
        self.sub_status = tk.Label(status_container, text="Loading components...", 
                                   font=("Segoe UI", 11), fg=THEME["text_light"], bg=THEME["bg_header"])
        self.sub_status.pack()
        
        content_frame = tk.Frame(root, bg=THEME["bg_main"])
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        log_label = tk.Label(content_frame, text="📋 Activity Log", 
                             font=("Segoe UI", 12, "bold"), fg=THEME["text_main"], bg=THEME["bg_main"])
        log_label.pack(anchor=tk.W, pady=(0, 5))
        
        log_border = tk.Frame(content_frame, bg=THEME["text_light"], bd=1)
        log_border.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_border, wrap=tk.WORD, 
                                                  height=15, font=("Consolas", 10),
                                                  bg=THEME["bg_log"], fg=THEME["text_main"],
                                                  bd=0, padx=15, pady=15,
                                                  insertbackground=THEME["text_main"])
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        button_frame = tk.Frame(root, bg=THEME["bg_main"])
        button_frame.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        btn_style = {
            "font": ("Segoe UI", 11, "bold"),
            "bd": 0,
            "relief": "flat",
            "cursor": "hand2",
            "padx": 25,
            "pady": 12
        }
        
        self.folder_btn = tk.Button(button_frame, text="📁 Select Folder", 
                                    command=self.select_folder,
                                    bg=THEME["accent_blue"], fg="white", 
                                    activebackground="#4a6396",
                                    **btn_style)
        self.folder_btn.pack(side=tk.LEFT, padx=5)
        
        self.start_btn = tk.Button(button_frame, text="▶️ Start", 
                                   command=self.start_system,
                                   bg=THEME["accent_green"], fg="white",
                                   activebackground="#3d6e4f",
                                   state=tk.DISABLED, **btn_style)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = tk.Button(button_frame, text="⏹️ Stop", 
                                  command=self.stop_system,
                                  bg=THEME["accent_red"], fg="white",
                                  activebackground="#a63f3f",
                                  state=tk.DISABLED, **btn_style)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        self.status_dot = tk.Label(button_frame, text="●", 
                                   font=("Segoe UI", 20), fg="#808080", bg=THEME["bg_main"])
        self.status_dot.pack(side=tk.RIGHT, padx=10)
        
        threading.Thread(target=self.initialize_components, daemon=True).start()
    
    def log(self, message, level="INFO"):
        timestamp = time.strftime("%H:%M:%S")
        colors = {
            "INFO": "#000000",
            "ERROR": "#c94c4c",
            "SUCCESS": "#2e7d32",
            "WARN": "#d68910"
        }
        prefix_colors = {"INFO": "💬", "ERROR": "❌", "SUCCESS": "✅", "WARN": "⚠️"}
        
        prefix = prefix_colors.get(level, "💬")
        color = colors.get(level, "#000000")
        
        self.log_text.tag_config(level, foreground=color)
        self.log_text.insert(tk.END, f"[{timestamp}] {prefix} ", "timestamp")
        self.log_text.insert(tk.END, f"{message}\n", level)
        self.log_text.see(tk.END)
        self.log_text.tag_config("timestamp", foreground="#999999")
        
    def update_status(self, main_text, sub_text="", color_override=None):
        final_color = color_override if color_override else THEME["text_main"]
        
        self.status_label.config(text=main_text, fg=final_color)
        self.sub_status.config(text=sub_text)
        
        dot_colors = {
            "INITIALIZING": "#808080", 
            "READY": THEME["accent_green"], 
            "MONITORING": THEME["accent_blue"],
            "LISTENING": "#e67e22",
            "CONFIRM": "#9b59b6",
            "STOPPED": THEME["accent_red"], 
            "ERROR": THEME["accent_red"]
        }
        
        for key, dot_color in dot_colors.items():
            if key in main_text:
                self.status_dot.config(fg=dot_color)
                break
        
    def select_folder(self):
        folder = filedialog.askdirectory(title="Select Folder to Search")
        if folder:
            self.search_path = folder
            self.log(f"Folder selected: {folder}")
            if self.components_ready:
                self.auto_start()
        else:
            self.search_path = os.getcwd()
            self.log(f"No folder selected. Using: {self.search_path}")
            if self.components_ready:
                self.auto_start()
    
    def auto_start(self):
        self.root.after(500, self.start_system)
    
    def initialize_components(self):
        self.log("Loading speech recognition models...")
        
        MODEL_PATH = resource_path("model")
        if not os.path.exists(MODEL_PATH):
            self.log(f"ERROR: Model not found at {MODEL_PATH}", "ERROR")
            self.update_status("❌ ERROR", "Model files missing!", THEME["accent_red"])
            return
        
        try:
            self.vosk_model = Model(MODEL_PATH)
            self.google_recognizer = sr.Recognizer()
            self.log("✓ Brains loaded (Vosk + Google)")
        except Exception as e:
            self.log(f"ERROR loading models: {e}", "ERROR")
            self.update_status("❌ ERROR", "Failed to load models", THEME["accent_red"])
            return
        
        self.log("Scanning for ESP32...")
        port = self.find_esp32_port()
        
        if not port:
            self.log("ERROR: ESP32 not found. Plug it in!", "ERROR")
            self.update_status("❌ ESP32 NOT FOUND", "Please plug in your device", THEME["accent_red"])
            return
        
        try:
            self.ser = serial.Serial(port, BAUD, timeout=0.1)
            time.sleep(2.5)
            self.ser.reset_input_buffer()
            self.log(f"✓ Connected to ESP32 on {port}")
        except Exception as e:
            self.log(f"ERROR connecting: {e}", "ERROR")
            self.update_status("❌ CONNECTION FAILED", "Could not connect to ESP32", THEME["accent_red"])
            return
        
        self.update_status("✅ READY", "Opening folder selector...", THEME["accent_green"])
        self.log("System ready! Opening folder selector...")
        self.folder_btn.config(state=tk.NORMAL)
        self.components_ready = True
        
        # Auto-open folder selector
        self.root.after(500, self.select_folder)
    
    def find_esp32_port(self):
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            if "CP210" in p.description or "CH340" in p.description or "USB" in p.description:
                self.log(f"Found ESP32 on {p.device}")
                return p.device
        if len(ports) > 0:
            return ports[-1].device
        return None
    
    def start_system(self):
        if not self.search_path:
            self.log("Please select a folder first!", "WARN")
            return
        
        self.running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.folder_btn.config(state=tk.DISABLED)
        
        self.update_status("🎤 MONITORING", "Say: 'Search for [filename]'", THEME["accent_blue"])
        self.log("🎤 Listening for voice commands...")
        threading.Thread(target=self.voice_loop, daemon=True).start()
    
    def stop_system(self):
        self.running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.folder_btn.config(state=tk.NORMAL)
        self.update_status("⏹️ STOPPED", "Click 'Start' to resume", THEME["accent_red"])
        self.log("System stopped.")
    
#ping
    def check_connection(self):
        """Ping Google DNS to see if internet is fast enough"""
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=1)
            return True
        except OSError:
            return False

    def get_text_from_audio(self, wav_filename):
        is_online = self.check_connection()

        if is_online:
            try:
                start_time = time.time()
                with sr.AudioFile(wav_filename) as source:
                    audio_data = self.google_recognizer.record(source)
                
                self.google_recognizer.energy_threshold = 300
                text = self.google_recognizer.recognize_google(audio_data, language="en-US")
                
                latency = time.time() - start_time
                if latency > MAX_GOOGLE_LATENCY:
                    self.log(f"Google slow ({latency:.1f}s), Using Vosk next time.", "WARN")
                
                self.log(f"--> [ONLINE] Google ({latency:.1f}s)", "SUCCESS")
                return text
                
            except sr.RequestError:
                self.log("Google API error. Falling back to Vosk.", "WARN")
                return self.get_text_from_audio_vosk(wav_filename)
            except sr.UnknownValueError:
                self.log("Google detected noise.", "WARN")
                return ""
            except Exception as e:
                self.log(f"Google Error: {e}. Switching to Vosk.", "WARN")
                return self.get_text_from_audio_vosk(wav_filename)
        else:
            self.log("No Internet. Using Offline Mode (Vosk).", "WARN")
            return self.get_text_from_audio_vosk(wav_filename)
    
    def get_text_from_audio_vosk(self, wav_filename):
        try:
            wf = wave.open(wav_filename, "rb")
            rec = KaldiRecognizer(self.vosk_model, wf.getframerate())
            rec.SetMaxAlternatives(0)
            rec.SetWords(False)
            
            while True:
                data = wf.readframes(4000)
                if len(data) == 0: break
                rec.AcceptWaveform(data)
            
            result = json.loads(rec.FinalResult())
            wf.close()
            
            text = result.get('text', '')
            if text: self.log(f"--> [OFFLINE] Vosk matched: '{text}'", "SUCCESS")
            return text
        except Exception as e:
            self.log(f"Vosk error: {e}", "ERROR")
            return ""

    def find_file(self, filename):
        self.log(f"Searching for: '{filename}' in {self.search_path}")
        self.ser.write(b"SEARCHING\n")
        
        matches = []
        for root, dirs, files in os.walk(self.search_path):
            for file in files:
                file_lower = file.lower()
                filename_lower = filename.lower()
                
                score = difflib.SequenceMatcher(None, filename_lower, file_lower).ratio()
                if filename_lower in file_lower: score = max(score, 0.8)
                
                if score > 0.4:
                    matches.append({'path': os.path.join(root, file), 'name': file, 'score': score})
        
        matches.sort(key=lambda x: x['score'], reverse=True)
        
        if len(matches) == 0:
            self.log("✗ No files found.", "WARN")
            self.ser.write(b"NOTFOUND\n")
            return None
        elif len(matches) == 1:
            self.log(f"✓ FOUND: {matches[0]['name']}", "SUCCESS")
            self.ser.write(b"FOUND\n")
            return matches[0]['path']
        else:
            self.log(f"✓ Found {len(matches)} matching files", "SUCCESS")
            self.ser.write(b"FOUND\n")
            return matches 

    def show_file_popup(self, items):
        """Show popup for voice confirmation - THEMED"""
        self.popup_window = tk.Toplevel(self.root)
        self.popup_window.title("File Found")
        self.popup_window.attributes("-topmost", True)
        self.popup_window.configure(bg=THEME["bg_header"]) # Themed
        
        if isinstance(items, str):
            filename = os.path.basename(items)
            self.popup_window.geometry("500x250")
            
            tk.Label(self.popup_window, text="📁 File Found!", 
                    font=("Segoe UI", 16, "bold"), fg=THEME["accent_green"], bg=THEME["bg_header"]).pack(pady=15)
            
            tk.Label(self.popup_window, text=filename, 
                    font=("Segoe UI", 12), fg=THEME["text_main"], bg=THEME["bg_header"]).pack(pady=5)
            
            tk.Label(self.popup_window, text="🎤 Say 'YES' / 'OPEN' to open\nSay 'NO' / 'CLOSE' to cancel", 
                    font=("Segoe UI", 14, "bold"), fg=THEME["accent_blue"], bg=THEME["bg_header"]).pack(pady=20)
            
        else:
            self.popup_window.geometry("500x400")
            tk.Label(self.popup_window, text=f"📁 Found {len(items)} Files", 
                    font=("Segoe UI", 16, "bold"), fg=THEME["accent_green"], bg=THEME["bg_header"]).pack(pady=10)
            
            list_frame = tk.Frame(self.popup_window, bg=THEME["bg_header"])
            list_frame.pack(fill=tk.BOTH, expand=True, padx=20)
            
            for i, match in enumerate(items[:5], 1):
                tk.Label(list_frame, text=f"{i}. {match['name']}", 
                        font=("Segoe UI", 10), fg=THEME["text_main"], bg=THEME["bg_header"], anchor="w").pack(fill=tk.X)
            
            tk.Label(self.popup_window, text="🎤 Say the NUMBER or 'CLOSE'", 
                    font=("Segoe UI", 12, "bold"), fg=THEME["accent_blue"], bg=THEME["bg_header"]).pack(pady=15)
        
        self.popup_window.protocol("WM_DELETE_WINDOW", lambda: None)

    def close_popup(self):
        try:
            if self.popup_window:
                self.popup_window.destroy()
                self.popup_window = None
        except: pass

    def voice_loop(self):
        buffer = bytearray()
        recording = False
        waiting_for_confirmation = False
        pending_file = None
        pending_matches = None
        
        while self.running:
            try:
                if self.ser.in_waiting > 0:
                    raw = self.ser.read(self.ser.in_waiting)
                    
                    if not recording:
                        try:
                            if "START_REC" in raw.decode('utf-8', errors='ignore'):
                                recording = True
                                buffer = bytearray()
                                self.log("🎙️ Recording...")
                                self.update_status("🎙️ LISTENING", "Speak now...", "#e67e22")
                        except: pass
                    
                    if recording:
                        buffer.extend(raw)
                        
                        if b"STOP_REC" in buffer:
                            recording = False
                            clean_audio = buffer.split(b"STOP_REC")[0]
                            
                            with wave.open(TEMP_WAV, 'wb') as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(16000)
                                wf.writeframes(clean_audio)
                            
                            try:
                                text = self.get_text_from_audio(TEMP_WAV)
                                
                                if text and text.strip() != "":
                                    self.log(f'You said: "{text}"', "SUCCESS")
                                    text = text.lower()
                                    
                                    if waiting_for_confirmation:
                                        if pending_file:
                                            if any(w in text for w in ["open", "yes", "yeah", "sure", "ok", "confirm"]):
                                                self.log("Opening file...")
                                                self.close_popup()
                                                try:
                                                    os.startfile(pending_file)
                                                    self.ser.write(b"OPENED\n")
                                                    self.log("✓ File opened!", "SUCCESS")
                                                except:
                                                    self.log("✗ Error opening file", "ERROR")
                                                waiting_for_confirmation = False
                                                pending_file = None
                                                self.update_status("🎤 MONITORING", "Say: 'Search for [filename]'", THEME["accent_blue"])
                                                
                                            elif any(w in text for w in ["close", "no", "nope", "cancel", "stop"]):
                                                self.log("Cancelled.")
                                                self.close_popup()
                                                self.ser.write(b"CANCELLED\n")
                                                waiting_for_confirmation = False
                                                pending_file = None
                                                self.update_status("🎤 MONITORING", "Say: 'Search for [filename]'", THEME["accent_blue"])
                                                
                                            else:
                                                self.log("Say 'YES' or 'NO'", "WARN")
                                        
                                        elif pending_matches:
                                            if any(w in text for w in ["close", "no", "cancel"]):
                                                self.log("Cancelled.")
                                                self.close_popup()
                                                waiting_for_confirmation = False
                                                pending_matches = None
                                                self.update_status("🎤 MONITORING", "Say: 'Search for [filename]'", THEME["accent_blue"])
                                            else:
                                                nums = {"one":1, "1":1, "two":2, "2":2, "three":3, "3":3, "four":4, "4":4, "five":5, "5":5}
                                                choice = None
                                                for w in text.split():
                                                    if w in nums: choice = nums[w]
                                                
                                                if choice and 1 <= choice <= len(pending_matches):
                                                    selected = pending_matches[choice-1]['path']
                                                    self.close_popup()
                                                    os.startfile(selected)
                                                    self.log(f"Opened file {choice}", "SUCCESS")
                                                    waiting_for_confirmation = False
                                                    pending_matches = None
                                                    self.update_status("🎤 MONITORING", "Say: 'Search for [filename]'", THEME["accent_blue"])
                                        
                                    else:
                                        valid_triggers = ["search", "find", "open"]
                                        found_trigger = False
                                        command_word = ""
                                        
                                        for trigger in valid_triggers:
                                            if trigger in text:
                                                found_trigger = True
                                                command_word = trigger
                                                break
                                        
                                        if found_trigger:
                                            filename = text.split(command_word, 1)[1].replace("for", "").strip()
                                            if filename:
                                                result = self.find_file(filename)
                                                if result:
                                                    waiting_for_confirmation = True
                                                    if isinstance(result, list):
                                                        pending_matches = result
                                                        pending_file = None
                                                        self.show_file_popup(result)
                                                        self.update_status("❓ CONFIRM", "Say the NUMBER", "#9b59b6")
                                                    else:
                                                        pending_file = result
                                                        pending_matches = None
                                                        self.show_file_popup(result)
                                                        self.update_status("❓ CONFIRM", "Say YES or NO", "#9b59b6")
                                                else:
                                                    self.update_status("🎤 MONITORING", "Say: 'Search for [filename]'", THEME["accent_blue"])
                                            else:
                                                self.update_status("🎤 MONITORING", "Say: 'Search for [filename]'", THEME["accent_blue"])
                                        else:
                                            self.update_status("🎤 MONITORING", "Say: 'Search for [filename]'", THEME["accent_blue"])
                                
                            except Exception as e:
                                self.log(f"Process Error: {e}", "ERROR")
                            buffer = bytearray()
                time.sleep(0.01)
            except Exception as e:
                self.log(f"Loop Error: {e}", "ERROR")
                break

if __name__ == "__main__":
    root = tk.Tk()
    app = VoiceFileFinderGUI(root)
    root.mainloop()
