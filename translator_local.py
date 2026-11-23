"""
本地翻譯程式 V4 - 使用 Ollama LLM 與 RapidOCR
功能：
1. OCR 純文字模式 (Ctrl+Shift+O) -> 自動複製到剪貼簿
2. 翻譯模式 (Ctrl+Shift+T) -> OCR + LLM 翻譯
3. AI 對話模式 -> 底部輸入框直接詢問
"""
import json
import os
import sys
import threading
import queue
import tkinter as tk
from tkinter import scrolledtext, messagebox
from typing import Tuple
from dataclasses import dataclass

import keyboard
import requests
import numpy as np
from PIL import ImageGrab
from rapidocr_onnxruntime import RapidOCR
import ctypes

# --- 設定預設值 ---
DEFAULT_OCR_DIR_DET = "model/ch_PP-OCRv5_mobile_det.onnx"  # OCR 偵測模型路徑
DEFAULT_OCR_DIR_REC = "model/ch_PP-OCRv5_rec_mobile_infer.onnx"  # OCR 識別模型路徑

DEFAULT_MODEL = "gemma3:1b" # 預設模型名稱
DEFAULT_OLLAMA_URL = "http://localhost:11434/" # 預設 Ollama API URL
DEFAULT_HOTKEY_TRANSALTE = "ctrl+shift+t" # 預設翻譯熱鍵
DEFAULT_HOTKEY_OCR = "ctrl+shift+o" # 預設 OCR 熱鍵
MAX_HISTORY_ROUNDS = 10  #記憶保留的回合數(10回合 = 20句對話)

DEFAULT_CHAT_PROMPT = "你是一個繁體中文的 AI 助理，回答請簡潔精確。"
DEFAULT_TRANSLATION_PROMPT = "將以下內容翻譯成繁體中文。專有名詞要保留原文。直接輸出翻譯結果，不要包含任何解釋："

# --- 配置層 ---
@dataclass
class AppConfig:
    model_name: str
    ollama_url: str
    hotkey_translate: str
    hotkey_ocr: str
    translate_prompt: str
    chat_prompt: str

    @classmethod
    def load_config(cls, path) -> 'AppConfig':
        defaults = {
            "model_name": DEFAULT_MODEL,
            "ollama_url": DEFAULT_OLLAMA_URL,
            "hotkey_translate": DEFAULT_HOTKEY_TRANSALTE,
            "hotkey_ocr": DEFAULT_HOTKEY_OCR,
            "translate_prompt": DEFAULT_TRANSLATION_PROMPT,
            "chat_prompt": DEFAULT_CHAT_PROMPT
        }

        # 如果是打包後的環境，強制將 config 路徑指到 exe 檔案旁邊，而不是內部暫存區
        if getattr(sys, 'frozen', False):
            path = os.path.join(os.path.dirname(sys.executable), path)

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 簡單的合併字典，以 defaults 為底
                config_data = {**defaults, **data}
        except Exception as e:
            print(f"[Config] 讀取錯誤: {e}，使用預設值")
            config_data = defaults

        return cls(
            model_name=config_data.get("model_name"),
            ollama_url=config_data.get("ollama_url"),
            hotkey_translate=config_data.get("hotkey_translate"),
            hotkey_ocr=config_data.get("hotkey_ocr"),
            translate_prompt=config_data.get("translate_prompt"),
            chat_prompt=config_data.get("chat_prompt")
        )

# --- 服務層 ---
class OCRService:
    def __init__(self):
        self.engine = None
        self._init_engine()

    def _init_engine(self):
        print("[OCR] 正在初始化 RapidOCR...")
        try:
            self.engine = RapidOCR(use_angle_cls=True, 
                                   det_model_path=DEFAULT_OCR_DIR_DET,
                                   rec_model_path=DEFAULT_OCR_DIR_REC) 
            print("[OCR] 初始化完成")
        except Exception as e:
            error_msg = f"RapidOCR 初始化失敗:\n{str(e)}"
            print(error_msg)
            messagebox.showerror("OCR 初始化錯誤", error_msg)
            self.engine = None

    def detect_text(self, region: Tuple[int, int, int, int]) -> str:
        if not self.engine:
            return "[錯誤: OCR 引擎未啟動]"
        
        try:
            x1, y1, x2, y2 = region
            screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            
            img_np = np.array(screenshot)
            result, _ = self.engine(img_np)
            
            if not result:
                return ""
            
            detected_texts = [line[1] for line in result]
            return "\n".join(detected_texts)
            
        except Exception as e:
            return f"[OCR 處理錯誤: {e}]"

class OllamaService:
    def __init__(self, app_config: AppConfig):
        self.app_config = app_config
        self.chat_history = [{"role": "system", "content": self.app_config.chat_prompt}]

    def _call_ollama(self, endpoint: str, payload: dict, stream: bool = False):
        """共用的底層 API 呼叫方法"""
        url = f"{self.app_config.ollama_url}{endpoint}"
        try:
            # 統一在這裡處理 timeout 與 post
            response = requests.post(url, json=payload, stream=stream, timeout=60)
            response.raise_for_status()
            return response
        except Exception as e:
            # 統一錯誤拋出，或者回傳特定錯誤物件
            raise RuntimeError(f"Ollama API Error: {e}")

    def translate(self, text: str) -> str:

        payload = {
            "model": self.app_config.model_name,
            "prompt": self.app_config.translate_prompt + text,
            "stream": False
        }
        try:
            # 呼叫共用方法
            response = self._call_ollama("/api/generate", payload, stream=False)
            return response.json().get("response", "[API 無回應]")
        except RuntimeError as e:
            return str(e)

    def chat(self, text: str):
        """
        對話模式：改用 /api/chat 接口 (支援記憶)
        實作：滑動視窗 (Sliding Window) 避免 Context 爆炸
        """
        if not text or not text.strip(): return ""
        
        # 1. 將使用者輸入加入歷史紀錄
        self.chat_history.append({"role": "user", "content": text})

        # 2. 滑動視窗機制：如果歷史過長，移除最舊的 (保留最新的 N*2 條)
        # 這裡 *2 是因為一問一答算 2 條訊息
        if len(self.chat_history) > MAX_HISTORY_ROUNDS * 2:
            self.chat_history = self.chat_history[-(MAX_HISTORY_ROUNDS * 2):]
        
        payload = {
            "model": self.app_config.model_name,
            "messages": self.chat_history, # 傳送整個歷史紀錄
            "stream": True
        }

        print(f"[LLM] 請求對話中 (歷史長度: {len(self.chat_history)})...")
        
        try:
            # [修改] 使用 stream=True
            response = self._call_ollama("/api/chat", payload, stream=True)
            
            full_response = "" # 用來累積完整的句子，以便存入歷史紀錄
            
            # [修改] 逐行讀取串流
            for line in response.iter_lines():
                if line:
                    try:
                        # Ollama 的串流是每一行一個 JSON 物件
                        body = json.loads(line.decode('utf-8'))
                        chunk = body.get("message", {}).get("content", "")
                        
                        if chunk:
                            full_response += chunk
                            yield chunk # <--- 將片段即時傳出去
                            
                        if body.get("done"):
                            # 結束時，將完整回應存入歷史
                            self.chat_history.append({"role": "assistant", "content": full_response})
                            
                    except json.JSONDecodeError:
                        continue
                            
        except Exception as e:
            # 發生錯誤時的處理 (稍微簡化，避免 yield 中斷太複雜)
            yield f"[傳輸錯誤: {str(e)}]"

    # [新增] 清除記憶的方法
    def clear_history(self):
        self.chat_history = [{"role": "system", "content": self.app_config.chat_prompt}]
        print("[LLM] 對話記憶已清除")

# --- UI 元件 ---
class SnippingTool(tk.Toplevel):
    """截圖工具"""
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.start_x = 0
        self.start_y = 0
        self.rect_id = None
        self.attributes('-fullscreen', True, '-alpha', 0.3, '-topmost', True)
        self.configure(bg='black')
        self.overrideredirect(True)
        self.canvas = tk.Canvas(self, cursor="cross", bg='black', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind('<Button-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        self.bind('<Escape>', lambda e: self.destroy())
        self.focus_force()

    def on_press(self, event):
        self.start_x, self.start_y = event.x, event.y

    def on_drag(self, event):
        if self.rect_id: self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, event.x, event.y,
            outline='red', width=2, fill='blue', stipple='gray50'
        )

    def on_release(self, event):
        x1, x2 = sorted([self.start_x, event.x])
        y1, y2 = sorted([self.start_y, event.y])
        self.destroy()
        if (x2 - x1) > 5 and (y2 - y1) > 5:
            self.callback((x1, y1, x2, y2))

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.app_config = AppConfig.load_config("config.json")
        self.ocr_service = OCRService()
        self.translator = OllamaService(self.app_config)
        self.queue = queue.Queue()
        self.current_mode = "translate" 
        
        self.setup_ui()
        self.setup_hotkeys()

        # 啟動後稍微延遲一下再進行防呆檢查，避免阻塞 UI 顯示
        self.after(500, self.check_ollama_status)  
        self.check_queue()

    def setup_ui(self):
        self.title(f"AI 螢幕翻譯工具 (Model: {self.app_config.model_name})")
        self.geometry("700x800")
        self.configure(bg='#f0f0f0')
        self.attributes('-topmost', True)

        # --- 頂部 Header ---
        header = tk.Frame(self, bg='#f0f0f0')
        header.pack(pady=10, fill=tk.X, padx=10)
        
        title_lbl = tk.Label(header, text="翻譯與文字擷取", font=('Microsoft JhengHei', 14, 'bold'), bg='#f0f0f0')
        title_lbl.pack(side=tk.TOP)

        info_frame = tk.Frame(header, bg='#f0f0f0')
        info_frame.pack(pady=5)
        tk.Label(info_frame, text=f"翻譯模式: {self.app_config.hotkey_translate}", bg='#e1f5fe', padx=5).pack(side=tk.LEFT, padx=5)
        tk.Label(info_frame, text=f"純文字模式: {self.app_config.hotkey_ocr}", bg='#e8f5e9', padx=5).pack(side=tk.LEFT, padx=5)

        # --- 按鈕區 ---
        btn_frame = tk.Frame(self, bg='#f0f0f0')
        btn_frame.pack(pady=5, fill=tk.X)
        
        tk.Button(btn_frame, text="擷取並翻譯文字", command=lambda: self.start_task("translate"),
                 bg='#2196F3', fg='white', font=('Microsoft JhengHei', 10), padx=10).pack(side=tk.LEFT, padx=20)
        
        tk.Button(btn_frame, text="擷取並複製文字", command=lambda: self.start_task("ocr_only"),
                 bg='#4CAF50', fg='white', font=('Microsoft JhengHei', 10), padx=10).pack(side=tk.LEFT, padx=5)

        tk.Button(btn_frame, text="清除畫面", command=self.clear_text,
                 bg='#9e9e9e', fg='white', padx=10).pack(side=tk.RIGHT, padx=20)
        
        tk.Button(btn_frame, text="忘記對話", command=self.clear_history,
                 bg='#FF7043', fg='white', padx=5).pack(side=tk.RIGHT, padx=5)

        # --- 設定區 ---
        opt_frame = tk.Frame(self, bg='#f0f0f0')
        opt_frame.pack(fill=tk.X, padx=20, pady=0)
        self.auto_merge_var = tk.BooleanVar(value=True)
        tk.Checkbutton(opt_frame, text="自動合併斷行 (適合文章)", variable=self.auto_merge_var, bg='#f0f0f0', font=('Microsoft JhengHei', 9)).pack(side=tk.LEFT)

        # --- 主要結果顯示區 ---
        self.result_text = scrolledtext.ScrolledText(
            self, wrap=tk.WORD, font=('Microsoft JhengHei', 11),
            bg='white', padx=10, pady=10
        )
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 10))
        
        # Tag 樣式設定
        self.result_text.tag_config('title_ocr', foreground='#2E7D32', font=('Microsoft JhengHei', 10, 'bold'))
        self.result_text.tag_config('title_trans', foreground='#1565C0', font=('Microsoft JhengHei', 10, 'bold'))
        self.result_text.tag_config('title_user', foreground='#E65100', font=('Microsoft JhengHei', 10, 'bold')) # 使用者提問顏色
        self.result_text.tag_config('title_ai', foreground='#6A1B9A', font=('Microsoft JhengHei', 10, 'bold'))   # AI 回應顏色
        self.result_text.tag_config('content', foreground='#333333')
        self.result_text.tag_config('separator', foreground='#cccccc')

        # --- 底部 AI 對話區 (新增功能) ---
        chat_frame = tk.Frame(self, bg='#e0e0e0', pady=5, padx=5)
        chat_frame.pack(fill=tk.X, side=tk.BOTTOM)

        chat_label = tk.Label(chat_frame, text="問 AI:", bg='#e0e0e0', font=('Microsoft JhengHei', 10, 'bold'))
        chat_label.pack(side=tk.LEFT, padx=5)

        self.chat_entry = tk.Entry(chat_frame, font=('Microsoft JhengHei', 11))
        self.chat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # 綁定 Enter 鍵送出
        self.chat_entry.bind('<Return>', self.on_chat_send)
        
        # 增加一個發送按鈕 (雖然 Enter 比較常用)
        send_btn = tk.Button(chat_frame, text="送出", command=self.on_chat_send, bg='#607D8B', fg='white', relief=tk.FLAT)
        send_btn.pack(side=tk.RIGHT, padx=5)

    def setup_hotkeys(self):
        try:
            keyboard.add_hotkey(self.app_config.hotkey_translate, lambda: self.trigger_from_thread("translate"))
            keyboard.add_hotkey(self.app_config.hotkey_ocr, lambda: self.trigger_from_thread("ocr_only"))
            print(f"[System] 熱鍵已註冊")
        except Exception as e:
            print(f"[System] 快捷鍵註冊失敗: {e}")

    # --- 新增：Ollama 狀態檢查 (防呆) ---
    def check_ollama_status(self):
        def _check_logic():
            ollama_url = self.app_config.ollama_url
            target_model = self.app_config.model_name
            
            print("[System] 正在檢查Ollama服務狀態與模型...")
            # 1. 檢查 Ollama 服務是否存活
            try:
                # 測試根目錄是否回應 (Ollama 通常回傳 "Ollama is running")
                requests.get(ollama_url, timeout=2)
                print("[System] Ollama服務運行中")
            except requests.exceptions.ConnectionError:
                self.queue.put(("error_msgbox", ("連線錯誤", "Ollama 尚未啟動或無法連線。\n請確認您已執行 'ollama serve' 或開啟應用程式。")))
                return

            # 2. 檢查目標模型是否存在
            print("[Ollama] 正在檢查模型列表...")
            try:
                tags_url = f"{ollama_url}/api/tags"
                res = requests.get(tags_url, timeout=5)
                if res.status_code == 200:
                    models_data = res.json().get("models", [])
                    # 取得所有已安裝的模型名稱 (包含 tag, e.g., "gemma3:1b")
                    installed_models = [m.get("name") for m in models_data]
                    print(f"[Ollama] 已安裝模型: {installed_models}")
                    
                    # 簡單的比對：檢查 target_model 是否包含在任一安裝的模型名稱中
                    # (有些 user 輸入 gemma3 但安裝的是 gemma3:latest，這裡做精確比對較保險，或者提示使用者)
                    if target_model not in installed_models:
                        # 嘗試寬鬆比對 (若設定 "gemma3" 但有 "gemma3:latest")
                        loose_match = any(target_model in m for m in installed_models)
                        if not loose_match:
                             self.queue.put(("error_msgbox", ("模型缺失", f"找不到模型: '{target_model}'\n\n您的設定 (或預設) 指定了此模型，但 Ollama 尚未下載。\n請執行: ollama pull {target_model}")))
                    
            except Exception as e:
                # 取得模型列表失敗，但不一定是嚴重錯誤，印出 log 即可
                print(f"[System] 無法檢查模型列表: {e}")

        # 在背景執行緒檢查，避免卡住 GUI
        threading.Thread(target=_check_logic, daemon=True).start()

    def trigger_from_thread(self, mode):
        self.after(0, lambda: self.start_task(mode))

    def start_task(self, mode):
        self.current_mode = mode
        self.withdraw()
        self.after(100, lambda: SnippingTool(self, self.on_region_selected))

    def on_region_selected(self, region):
        self.deiconify()
        if region:
            mode_text = "翻譯" if self.current_mode == "translate" else "文字擷取"
            self.result_text.insert(tk.END, f"\n--- 正在進行{mode_text} ---\n", 'separator')
            threading.Thread(target=self.process_pipeline, args=(region,), daemon=True).start()

    def process_pipeline(self, region):
        self.config(cursor="watch")
        try:
            # 1. OCR
            text = self.ocr_service.detect_text(region)
            if not text.strip():
                self.queue.put(("info", "未偵測到文字"))
                return
            
            if self.auto_merge_var.get():
                text = text.replace("\n", " ")

            self.queue.put(("ocr_result", text))

            # 2. Action
            if self.current_mode == "ocr_only":
                self.queue.put(("copy", text))
                self.queue.put(("info", ">> 文字已複製到剪貼簿"))
            
            elif self.current_mode == "translate":
                trans_text = self.translator.translate(text)
                self.queue.put(("trans_result", trans_text))
        except Exception as e:
            self.queue.put(("error", str(e)))
        finally:
            self.config(cursor="")

    # --- 新增：處理對話輸入 ---
    def on_chat_send(self, event=None):
        user_input = self.chat_entry.get().strip()
        if not user_input:
            return
        
        # 清空輸入框
        self.chat_entry.delete(0, tk.END)
        
        # 顯示使用者問題
        self.queue.put(("chat_user", user_input))
        
        # 啟動執行緒處理 AI 回應
        threading.Thread(target=self.process_chat_thread, args=(user_input,), daemon=True).start()

    def process_chat_thread(self, user_input):
        self.config(cursor="watch") # 轉圈圈
        try:
            # 1. 先通知 UI 顯示「AI 回應」的標題 (不帶內容)
            self.queue.put(("chat_ai_start", "")) 
            
            # 2. 迴圈接收串流片段
            # self.translator.chat 現在是一個生成器，所以用 for 讀取
            for chunk in self.translator.chat(user_input):
                self.queue.put(("chat_ai_chunk", chunk)) # 送出片段
            
            # 3. 全部講完後，送出結束訊號 (印分隔線)
            self.queue.put(("chat_ai_end", ""))
            
        except Exception as e:
            self.queue.put(("error", f"對話失敗: {e}"))
        finally:
            print("[LLM] 對話處理完成")
            self.config(cursor="")


    def check_queue(self):
        try:
            while True:
                msg_type, content = self.queue.get_nowait()
                
                if msg_type == "ocr_result":
                    self.result_text.insert(tk.END, "【辨識內容】\n", 'title_ocr')
                    self.result_text.insert(tk.END, f"{content}\n\n", 'content')
                
                elif msg_type == "trans_result":
                    self.result_text.insert(tk.END, "【翻譯結果】\n", 'title_trans')
                    self.result_text.insert(tk.END, f"{content}\n", 'content')
                    self.result_text.insert(tk.END, "-" * 30 + "\n", 'separator')
                
                elif msg_type == "chat_user":
                    self.result_text.insert(tk.END, "\n【使用者提問】\n", 'title_user')
                    self.result_text.insert(tk.END, f"{content}\n", 'content')

                # [修改] 拆分成 Start / Chunk / End 三個階段
                elif msg_type == "chat_ai_start":
                    # 只印標題
                    self.result_text.insert(tk.END, "【AI 回應】\n", 'title_ai')
                
                elif msg_type == "chat_ai_chunk":
                    # 印出片段 (注意：不要加 \n，因為片段是連續的)
                    self.result_text.insert(tk.END, content, 'content')
                    self.result_text.see(tk.END) # 自動捲動到底部
                
                elif msg_type == "chat_ai_end":
                    # 結束，印換行與分隔線
                    self.result_text.insert(tk.END, "\n", 'content')
                    self.result_text.insert(tk.END, "-" * 30 + "\n", 'separator')

                elif msg_type == "copy":
                    self.clipboard_clear()
                    self.clipboard_append(content)
                    self.update() 
                
                elif msg_type == "info":
                    self.result_text.insert(tk.END, f"{content}\n", 'separator')
                
                elif msg_type == "error":
                    self.result_text.insert(tk.END, f"[錯誤] {content}\n", 'separator')

                elif msg_type == "error_msgbox":
                    title, msg = content
                    messagebox.showerror(title, msg)           
                
                self.result_text.see(tk.END)
        except queue.Empty:
            pass
        finally:
            self.after(100, self.check_queue)

    def clear_text(self):
        self.result_text.delete(1.0, tk.END)

    def clear_history(self):
        self.translator.clear_history()
        self.queue.put(("info", ">> AI 對話記憶已清除"))

if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        os.chdir(sys._MEIPASS)

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    
    app = MainWindow()
    try:
        app.mainloop()
    finally:
        keyboard.unhook_all()