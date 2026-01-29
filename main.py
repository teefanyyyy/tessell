import serial
import serial.tools.list_ports
import time
import os
import shutil
import wave
import difflib
import json
import sys
import threading
import socket
import speech_recognition as sr
from vosk import Model, KaldiRecognizer
import customtkinter as ctk 
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox

try:
    import docx
except ImportError:
    docx = None
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None
try:
    from pptx import Presentation
except ImportError:
    Presentation = None

BAUD = 921600                
TEMP_WAV = "temp_audio.wav"
MAX_GOOGLE_LATENCY = 2.0 

def text_to_int(text):
    text = text.lower()
    num_map = {
        'one': 1, 'won': 1, '1': 1, 'two': 2, 'to': 2, 'too': 2, '2': 2,
        'three': 3, '3': 3, 'four': 4, 'for': 4, '4': 4, 'five': 5, '5': 5,
        'six': 6, '6': 6, 'seven': 7, '7': 7, 'eight': 8, '8': 8, 'nine': 9, '9': 9,
        'ten': 10, '10': 10, 'eleven': 11, '11': 11, 'twelve': 12, '12': 12,
        'thirteen': 13, '13': 13, 'fourteen': 14, '14': 14, 'fifteen': 15, '15': 15,
        'sixteen': 16, '16': 16, 'seventeen': 17, '17': 17, 'eighteen': 18, '18': 18,
        'nineteen': 19, '19': 19, 'twenty': 20, '20': 20,
        'thirty': 30, '30': 30, 'forty': 40, '40': 40, 'fifty': 50, '50': 50
    }
    for word in text.split():
        if word in num_map:
            total = num_map[word]
            if "twenty" in text and word in ['one','two','three','four','five','six','seven','eight','nine']:
                return 20 + num_map[word]
            if "thirty" in text and word in ['one','two','three','four','five','six','seven','eight','nine']:
                return 30 + num_map[word]
            if "forty" in text and word in ['one','two','three','four','five','six','seven','eight','nine']:
                return 40 + num_map[word]
            return total
    return None

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_file_content(filepath):
    content = ""
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == '.txt':
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        
        elif ext == '.docx' and docx:
            doc = docx.Document(filepath)
            content = " ".join([p.text for p in doc.paragraphs])
            
        elif ext == '.pdf' and PyPDF2:
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    content += page.extract_text() + " "
        
        elif (ext == '.pptx' or ext == '.ppt') and Presentation:
            prs = Presentation(filepath)
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        content += shape.text + " "
    except: pass
    return content.lower()

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

class VoiceFileFinderGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.COLOR_BG = "#2b2024"         
        self.COLOR_PANEL = "#3d2e33"      
        self.COLOR_ACCENT = "#fdd9dd"     
        self.COLOR_ACCENT_HOVER = "#eec8cc"
        self.COLOR_BTN_TEXT = "#2b2024"
        self.COLOR_SUCCESS = "#77dd77"
        self.COLOR_ERROR = "#ff6961"

        self.title("tessell")
        self.geometry("900x650")
        self.configure(fg_color=self.COLOR_BG)
        
        self.search_path = None
        self.ser = None
        self.running = False
        self.popup_window = None
        self.command_window = None 
        self.components_ready = False
        self.vosk_model = None
        self.google_recognizer = None
        self.pending_matches = None 

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=250, corner_radius=0, fg_color=self.COLOR_PANEL)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(6, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar, text="tessell", 
                                     font=ctk.CTkFont(size=28, weight="bold"), text_color=self.COLOR_ACCENT)
        self.logo_label.grid(row=0, column=0, padx=20, pady=(40, 20))

        self.status_btn = ctk.CTkButton(self.sidebar, text="INITIALIZING", fg_color="#555555",
                                      text_color="white", hover=False, height=30, corner_radius=20)
        self.status_btn.grid(row=1, column=0, padx=20, pady=10)

        self.folder_btn = ctk.CTkButton(self.sidebar, text="📁 Select Folder", command=self.select_folder,
                                      fg_color=self.COLOR_ACCENT, text_color=self.COLOR_BTN_TEXT,
                                      hover_color=self.COLOR_ACCENT_HOVER, font=("Segoe UI", 14, "bold"))
        self.folder_btn.grid(row=2, column=0, padx=20, pady=20, sticky="ew")

        self.start_btn = ctk.CTkButton(self.sidebar, text="▶ START", command=self.start_system, state="disabled",
                                     fg_color=self.COLOR_SUCCESS, text_color="#1a1a1a", font=("Segoe UI", 14, "bold"))
        self.start_btn.grid(row=3, column=0, padx=20, pady=10, sticky="ew")

        self.stop_btn = ctk.CTkButton(self.sidebar, text="⏹ STOP", command=self.stop_system, state="disabled",
                                    fg_color=self.COLOR_ERROR, text_color="white", font=("Segoe UI", 14, "bold"))
        self.stop_btn.grid(row=4, column=0, padx=20, pady=10, sticky="ew")

        self.help_btn = ctk.CTkButton(self.sidebar, text="❓ Commands", command=self.show_commands,
                                    fg_color="#555555", hover_color="#666666", font=("Segoe UI", 12))
        self.help_btn.grid(row=5, column=0, padx=20, pady=20, sticky="ew")

        self.info_label = ctk.CTkLabel(self.sidebar, text="Capstone 2025", text_color="gray60")
        self.info_label.grid(row=7, column=0, padx=20, pady=20)

        self.main_area = ctk.CTkFrame(self, fg_color="transparent")
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_area.grid_rowconfigure(1, weight=1)
        self.main_area.grid_columnconfigure(0, weight=1)

        self.console_label = ctk.CTkLabel(self.main_area, text="Activity Log", 
                                        font=("Segoe UI", 18, "bold"), text_color=self.COLOR_ACCENT)
        self.console_label.grid(row=0, column=0, sticky="w", pady=(0, 10))

        self.log_text = ctk.CTkTextbox(self.main_area, font=("Consolas", 12), text_color="#e0e0e0",
                                     fg_color="#1a1215", border_color=self.COLOR_ACCENT, border_width=1)
        self.log_text.grid(row=1, column=0, sticky="nsew")
        
        threading.Thread(target=self.initialize_components, daemon=True).start()

    def log(self, message, level="INFO"):
        try:
            line_count = int(self.log_text.index('end-1c').split('.')[0])
            if line_count > 100: 
                self.log_text.delete("1.0", "2.0")
        except: pass

        timestamp = time.strftime("%H:%M:%S")
        prefix = "💬"
        if level == "ERROR": prefix = "❌"
        if level == "SUCCESS": prefix = "✅"
        if level == "WARN": prefix = "⚠️"
        
        full_msg = f"[{timestamp}] {prefix} {message}\n"
        self.log_text.insert("end", full_msg)
        self.log_text.see("end")
        
    def update_status(self, text):
        color_map = {"INITIALIZING":"#808080", "READY":self.COLOR_SUCCESS, "LISTENING":"#fdfd96",
                     "MONITORING":"#00d4ff", "CONFIRM":self.COLOR_ACCENT, "STOPPED":self.COLOR_ERROR, "ERROR":self.COLOR_ERROR}
        use_color = "#808080"
        for k,v in color_map.items(): 
            if k in text: use_color = v
        self.status_btn.configure(text=text, fg_color=use_color, text_color="#1a1a1a" if "LISTENING" in text or "READY" in text else "white")

    def show_commands(self):
        if self.command_window is None or not self.command_window.winfo_exists():
            self.command_window = ctk.CTkToplevel(self)
            self.command_window.title("Voice Commands")
            self.command_window.geometry("400x500")
            self.command_window.attributes("-topmost", True)
            self.command_window.configure(fg_color=self.COLOR_BG)
            
            ctk.CTkLabel(self.command_window, text="🎙 Command List", font=("Segoe UI", 20, "bold"), text_color=self.COLOR_ACCENT).pack(pady=15)
            
            cmds = [
                ("SEARCHING", ""),
                ("Find file name [Apple]", "Finds filename"),
                ("Find file with [Math]", "Reads inside files for text"),
                ("", ""),
                ("ORGANIZING", ""),
                ("Organize Alphabetically", "Sorts files A-Z into folders"),
                ("Organize by Subject", "Sorts by content (Math, Sci...)"),
                ("", ""),
                ("SELECTION", ""),
                ("Say 'One', 'Two'...", "Selects a file from list"),
                ("Say 'Close'", "Cancels selection")
            ]
            
            scroll = ctk.CTkScrollableFrame(self.command_window, fg_color="transparent")
            scroll.pack(fill="both", expand=True, padx=10, pady=10)
            
            for cmd, desc in cmds:
                if desc == "":
                    ctk.CTkLabel(scroll, text=cmd, font=("Segoe UI", 14, "bold"), text_color="#77dd77", anchor="w").pack(fill="x", pady=(10,5))
                else:
                    f = ctk.CTkFrame(scroll, fg_color=self.COLOR_PANEL)
                    f.pack(fill="x", pady=2)
                    ctk.CTkLabel(f, text=f"🗣 \"{cmd}\"", font=("Segoe UI", 12, "bold"), text_color="white", anchor="w").pack(fill="x", padx=10, pady=(5,0))
                    ctk.CTkLabel(f, text=desc, font=("Segoe UI", 11), text_color="gray", anchor="w").pack(fill="x", padx=10, pady=(0,5))
        else:
            self.command_window.lift()
            self.command_window.focus()

    def initialize_components(self):
        MODEL_PATH = resource_path("model")
        if not os.path.exists(MODEL_PATH):
            self.log(f"ERROR: Model missing", "ERROR")
            return
        
        try:
            self.vosk_model = Model(MODEL_PATH)
            self.google_recognizer = sr.Recognizer()
            self.log("Brains Loaded Successfully", "SUCCESS")
        except Exception as e:
            self.log(f"Error loading brains: {e}", "ERROR")
            return

        self.connect_to_esp32()

        self.update_status("✅ READY")
        self.folder_btn.configure(state="normal")
        self.components_ready = True
        self.after(500, self.select_folder)

    def find_esp32_port(self):
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            if any(x in p.description for x in ["CP210", "CH340", "USB"]): return p.device
        if ports: return ports[-1].device
        return None

    def connect_to_esp32(self):
        if self.ser and self.ser.is_open:
            try: self.ser.close()
            except: pass
            
        port = self.find_esp32_port()
        if not port:
            self.log("ESP32 Not Found. Plug it in.", "WARN")
            self.update_status("❌ NO DEVICE")
            return False
            
        try:
            self.ser = serial.Serial(port, BAUD, timeout=0.1)
            time.sleep(2) # Wait for reboot
            self.ser.reset_input_buffer()
            self.log(f"Connected to {port}", "SUCCESS")
            return True
        except:
            self.log("Connection Failed", "ERROR")
            self.update_status("❌ ERROR")
            return False

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.search_path = folder
            self.log(f"Target: {folder}")
            if self.components_ready: self.auto_start()

    def auto_start(self): self.after(500, self.start_system)

    def start_system(self):
        if not self.search_path: return
        
        if not self.ser or not self.ser.is_open:
            self.log("Not connected. Scanning...", "WARN")
            if not self.connect_to_esp32(): return

        try:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
        except:
            self.log("Reconnecting...", "WARN")
            if not self.connect_to_esp32(): return

        self.running = True
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.folder_btn.configure(state="disabled")
        self.update_status("🎤 MONITORING")
        threading.Thread(target=self.voice_loop, daemon=True).start()

    def stop_system(self):
        self.running = False
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.folder_btn.configure(state="normal")
        self.update_status("⏹ STOPPED")

    def check_connection(self):
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=1)
            return True
        except: return False

    def get_text_from_audio(self, wav_filename):
        if self.check_connection():
            try:
                with sr.AudioFile(wav_filename) as source:
                    audio = self.google_recognizer.record(source)
                self.google_recognizer.energy_threshold = 300
                text = self.google_recognizer.recognize_google(audio)
                self.log(f"Online: '{text}'", "SUCCESS")
                return text
            except:
                return self.get_text_vosk(wav_filename)
        else:
            return self.get_text_vosk(wav_filename)

    def get_text_vosk(self, wav_filename):
        try:
            wf = wave.open(wav_filename, "rb")
            rec = KaldiRecognizer(self.vosk_model, wf.getframerate())
            while True:
                data = wf.readframes(4000)
                if len(data) == 0: break
                rec.AcceptWaveform(data)
            res = json.loads(rec.FinalResult())
            text = res.get('text', '')
            if text: self.log(f"Offline: '{text}'", "SUCCESS")
            return text
        except: return ""

    def voice_loop(self):
        buffer = bytearray()
        recording = False
        waiting_for_confirmation = False
        
        while self.running:
            try:
                try:
                    if self.ser.in_waiting > 0:
                        raw = self.ser.read(self.ser.in_waiting)
                    else:
                        time.sleep(0.01)
                        continue
                except (OSError, serial.SerialException):
                    self.log("⚠️ Device Disconnected!", "ERROR")
                    self.update_status("❌ DISCONNECTED")
                    self.stop_system()
                    self.ser = None
                    break 

                if not recording and "START_REC" in raw.decode('utf-8','ignore'):
                    recording = True
                    buffer = bytearray()
                    self.update_status("🎙 LISTENING")
                
                if recording:
                    buffer.extend(raw)
                    if b"STOP_REC" in buffer:
                        recording = False
                        clean = buffer.split(b"STOP_REC")[0]
                        with wave.open(TEMP_WAV, 'wb') as wf:
                            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
                            wf.writeframes(clean)
                        
                        try:
                            text = self.get_text_from_audio(TEMP_WAV)
                            if text: 
                                text = text.lower()
                                
                                if waiting_for_confirmation and self.pending_matches:
                                    if any(w in text for w in ["close", "cancel", "no", "stop"]):
                                        self.log("Cancelled.")
                                        self.close_popup()
                                        self.pending_matches = None
                                        waiting_for_confirmation = False
                                        self.update_status("🎤 MONITORING")
                                    else:
                                        choice = text_to_int(text)
                                        if len(self.pending_matches) == 1 and any(w in text for w in ["yes", "open", "sure"]): choice = 1
                                        if choice and 1 <= choice <= len(self.pending_matches):
                                            selected = self.pending_matches[choice-1]['path']
                                            self.log(f"Opening: {self.pending_matches[choice-1]['name']}", "SUCCESS")
                                            self.close_popup()
                                            os.startfile(selected)
                                            self.ser.write(b"FOUND\n") 
                                            self.pending_matches = None
                                            waiting_for_confirmation = False
                                            self.update_status("🎤 MONITORING")
                                        else:
                                            self.log(f"Say a number 1-{len(self.pending_matches)}", "WARN")

                                else:
                                    self.process_command(text)
                                    if self.pending_matches: 
                                        waiting_for_confirmation = True

                            else: self.update_status("🎤 MONITORING")
                        except Exception as e:
                            self.log(f"Logic Error: {e}", "ERROR")
                        buffer = bytearray()
            except: break

    def process_command(self, text):
        if "arrange" in text or "organize" in text:
            if "alphabet" in text: self.organize_alphabetically()
            elif "subject" in text or "content" in text: self.organize_by_subject()
            else: self.log("Say 'Alphabetically' or 'By Subject'", "WARN")
        elif "find" in text or "search" in text:
            clean = text.replace("search", "").replace("find", "").replace("for", "").strip()
            if not clean:
                self.log("Say filename (e.g. 'Search for Notes')", "WARN")
                return 
            if "with" in clean:
                parts = clean.split("with")
                if len(parts) > 1 and parts[1].strip(): self.find_by_content(parts[1].strip())
                else: self.log("Say a word after 'with'", "WARN")
            else:
                keyword = clean.replace("file name", "").strip()
                if keyword: self.find_by_name(keyword)
                else: self.log("Say the filename", "WARN")
        else: self.update_status("🎤 MONITORING")

    def organize_alphabetically(self):
        self.log("Sorting files A-Z...", "INFO")
        self.ser.write(b"SEARCHING\n")
        count = 0
        try:
            for file in os.listdir(self.search_path):
                if os.path.isfile(os.path.join(self.search_path, file)):
                    first = file[0].upper()
                    if not first.isalpha(): first = "#"
                    target = os.path.join(self.search_path, first)
                    if not os.path.exists(target): os.makedirs(target)
                    shutil.move(os.path.join(self.search_path, file), os.path.join(target, file))
                    count += 1
            self.log(f"Moved {count} files.", "SUCCESS")
            self.ser.write(b"FOUND\n")
        except Exception as e: self.log(f"Error organizing: {e}", "ERROR")

    def organize_by_subject(self):
        self.log("Organizing by Subject...", "INFO")
        self.ser.write(b"SEARCHING\n")
        subjects = {"Math": ["algebra", "geometry", "math"], "Science": ["biology", "chemistry", "physics"], "History": ["war", "history", "ancient"], "English": ["essay", "novel", "literature"], "Programming": ["code", "python", "java"]}
        count = 0
        try:
            for file in os.listdir(self.search_path):
                full = os.path.join(self.search_path, file)
                if os.path.isfile(full):
                    best = "Misc"
                    content = get_file_content(full)
                    combo = (file + " " + content).lower()
                    for sub, keys in subjects.items():
                        if any(k in combo for k in keys):
                            best = sub
                            break
                    target = os.path.join(self.search_path, best)
                    if not os.path.exists(target): os.makedirs(target)
                    try:
                        shutil.move(full, os.path.join(target, file))
                        count += 1
                    except: pass
            self.log(f"Organized {count} files.", "SUCCESS")
            self.ser.write(b"FOUND\n")
        except Exception as e: self.log(f"Error: {e}", "ERROR")

    def find_by_content(self, keyword):
        self.log(f"Reading content for '{keyword}'...", "INFO")
        self.ser.write(b"SEARCHING\n")
        matches = []
        for root, dirs, files in os.walk(self.search_path):
            for file in files:
                full = os.path.join(root, file)
                if keyword in file.lower():
                    matches.append({'path': full, 'name': file, 'score': 100})
                    continue
                if keyword in get_file_content(full):
                    matches.append({'path': full, 'name': file, 'score': 90})
        self.handle_results(matches)

    def find_by_name(self, filename):
        self.log(f"Searching: '{filename}'", "INFO")
        self.ser.write(b"SEARCHING\n")
        matches = []
        for root, dirs, files in os.walk(self.search_path):
            for file in files:
                score = difflib.SequenceMatcher(None, filename, file.lower()).ratio()
                if filename in file.lower(): score = max(score, 0.8)
                if score > 0.4: matches.append({'path': os.path.join(root, file), 'name': file, 'score': score})
        self.handle_results(matches)

    def handle_results(self, matches):
        matches.sort(key=lambda x: x['score'], reverse=True)
        if matches:
            self.pending_matches = matches
            self.ser.write(b"FOUND\n")
            self.after(0, lambda: self.show_modern_popup(matches))
        else:
            self.ser.write(b"NOTFOUND\n")
            self.log("No matches found.", "WARN")
            self.pending_matches = None

    def show_modern_popup(self, items):
        if self.popup_window: 
            try: self.popup_window.destroy()
            except: pass
        self.popup_window = ctk.CTkToplevel(self)
        self.popup_window.title("Results")
        self.popup_window.geometry("600x500")
        self.popup_window.attributes("-topmost", True)
        self.popup_window.configure(fg_color=self.COLOR_BG)
        ctk.CTkLabel(self.popup_window, text=f"📂 Found {len(items)} Files", font=("Segoe UI", 20, "bold"), text_color=self.COLOR_SUCCESS).pack(pady=15)
        scroll_frame = ctk.CTkScrollableFrame(self.popup_window, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=10)
        for i, match in enumerate(items):
            btn_text = f"{i+1}. {match['name']}"
            card = ctk.CTkLabel(scroll_frame, text=btn_text, anchor="w", fg_color="#4a3b40", corner_radius=10, height=40, font=("Segoe UI", 12), text_color="white")
            card.pack(fill="x", pady=5, padx=5)
        ctk.CTkLabel(self.popup_window, text="🎤 Say 'ONE', 'TWELVE', 'OPEN ONE'...", font=("Segoe UI", 14), text_color=self.COLOR_ACCENT).pack(pady=15)
        self.update_status("❓ CONFIRM")
        
    def close_popup(self):
        try:
            if self.popup_window:
                self.popup_window.destroy()
                self.popup_window = None
        except: pass

if __name__ == "__main__":
    app = VoiceFileFinderGUI()
    app.mainloop()
