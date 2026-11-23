"""
翻譯程式 - 使用快捷鍵框選區域進行 OCR 和翻譯
"""
import asyncio
import json
import os
import sys
import threading
import tkinter as tk
from tkinter import scrolledtext
from typing import Optional, Tuple

import keyboard
import pytesseract
from PIL import Image, ImageGrab, ImageEnhance

import aiohttp

class TranslationApp:
    def __init__(self):
        self.hotkey = 'ctrl+shift+t'
        self.api_key: Optional[str] = None
        self.root: Optional[tk.Tk] = None
        self.result_text: Optional[scrolledtext.ScrolledText] = None
        self.is_selecting = False
        
        # 載入設定
        self.load_api_key()
        self.init_tesseract()
    
    def init_tesseract(self):
        """初始化 Tesseract OCR (支援攜帶版路徑)"""
        # 取得目前程式所在的資料夾路徑
        # 如果是打包後的 exe，路徑會在 sys.executable 旁邊
        # 如果是原始碼運行，路徑會在 __file__ 旁邊
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))

        # 設定攜帶版 Tesseract 的路徑 (預設在程式旁邊的 Tesseract-OCR 資料夾)
        tesseract_dir = os.path.join(base_path, 'Tesseract-OCR')
        manual_path = os.path.join(tesseract_dir, 'tesseract.exe')
        tessdata_dir = os.path.join(tesseract_dir, 'tessdata')
        
        # 檢查是否存在
        if os.path.exists(manual_path):
            pytesseract.pytesseract.tesseract_cmd = manual_path
            os.environ['TESSDATA_PREFIX'] = tessdata_dir
            print(f"已載入攜帶版 Tesseract: {manual_path}")
        else:
            # 如果找不到攜帶版，才嘗試系統預設路徑 (備援)
            print(f"在 {manual_path} 找不到攜帶版 Tesseract，嘗試系統預設...")
            # (這裡可以保留原本的 common_paths 邏輯作為備案，或直接報錯)
            manual_path = r'C:\Users\Albert\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'
            tessdata_dir = r'C:\Users\Albert\AppData\Local\Programs\Tesseract-OCR\tessdata'
            pytesseract.pytesseract.tesseract_cmd = manual_path
            os.environ['TESSDATA_PREFIX'] = tessdata_dir
            print(f"載入預設 Tesseract: {manual_path}")

    def load_api_key(self):
        """從環境變數或配置文件載入 API key"""
        self.api_key = os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            try:
                if os.path.exists('config.json'):
                    with open('config.json', 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        self.api_key = config.get('gemini_api_key')
            except Exception as e:
                print(f"讀取配置文件錯誤: {e}")
        
        if self.api_key:
            # 去除可能存在的首尾空白，這常導致 API 錯誤
            self.api_key = self.api_key.strip()
        else:
            print("警告: 未找到 GEMINI_API_KEY")

    def create_gui(self):
        """創建結果顯示視窗"""
        self.root = tk.Tk()
        self.root.title("翻譯結果")
        self.root.geometry("800x680")
        self.root.configure(bg='#f0f0f0')
        
        # 標題
        tk.Label(
            self.root, text="翻譯結果", font=('Microsoft JhengHei', 16, 'bold'),
            bg='#f0f0f0', fg='#333'
        ).pack(pady=10)
        
        # 說明
        tk.Label(
            self.root, text=f"快捷鍵: {self.hotkey.upper()} | 框選區域後自動翻譯",
            font=('Microsoft JhengHei', 10), bg='#f0f0f0', fg='#666'
        ).pack(pady=5)

        # --- 語言選擇區 ---
        lang_frame = tk.Frame(self.root, bg='#f0f0f0')
        lang_frame.pack(pady=2)
        tk.Label(lang_frame, text="辨識模式：", bg='#f0f0f0', font=('Microsoft JhengHei', 10)).pack(side=tk.LEFT)

        if not hasattr(self, 'ocr_lang_var'):
            self.ocr_lang_var = tk.StringVar(value='jpn')
        
        for text, val in [("日文專用", "jpn"), ("英文專用", "eng"), ("日英混合", "jpn+eng")]:
            tk.Radiobutton(
                lang_frame, text=text, variable=self.ocr_lang_var, value=val,
                bg='#f0f0f0', font=('Microsoft JhengHei', 10)
            ).pack(side=tk.LEFT, padx=5)

        # --- 文字方向選擇區 ---
        dir_frame = tk.Frame(self.root, bg='#f0f0f0')
        dir_frame.pack(pady=2)
        tk.Label(dir_frame, text="文字方向：", bg='#f0f0f0', font=('Microsoft JhengHei', 10)).pack(side=tk.LEFT)
        
        if not hasattr(self, 'ocr_direction_var'):
            self.ocr_direction_var = tk.StringVar(value='h')
            
        for text, val in [("橫書", "h"), ("直書", "v")]:
            tk.Radiobutton(
                dir_frame, text=text, variable=self.ocr_direction_var, value=val,
                bg='#f0f0f0', font=('Microsoft JhengHei', 10)
            ).pack(side=tk.LEFT, padx=5)
        
        # 結果顯示區域
        self.result_text = scrolledtext.ScrolledText(
            self.root, wrap=tk.WORD, font=('Microsoft JhengHei', 11),
            bg='white', fg='#333', padx=10, pady=10,
            relief=tk.SUNKEN, borderwidth=2
        )
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 清除按鈕
        tk.Button(
            self.root, text="清除結果", command=self.clear_results,
            font=('Microsoft JhengHei', 10), bg='#4CAF50', fg='white',
            relief=tk.RAISED, padx=20, pady=5
        ).pack(pady=5)
        
        self.root.attributes('-topmost', True)
        self.root.lift()
        self.root.focus_force()
    
    def clear_results(self):
        if self.result_text:
            self.result_text.delete(1.0, tk.END)
    
    def append_result(self, text: str, is_original: bool = True):
        if not self.result_text: return
        
        if is_original:
            self.result_text.insert(tk.END, f"【原文】\n{text}\n\n", 'original')
            self.result_text.tag_config('original', foreground='#333')
        else:
            self.result_text.insert(tk.END, f"【翻譯】\n{text}\n\n", 'translation')
            self.result_text.tag_config('translation', foreground='#0066cc', font=('Microsoft JhengHei', 11, 'bold'))
        
        self.result_text.see(tk.END)
        self.root.update()
    
    def select_region(self) -> Optional[Tuple[int, int, int, int]]:
        if self.is_selecting: return None
        self.is_selecting = True
        
        try:
            selection_window = tk.Toplevel()
            selection_window.attributes('-fullscreen', True, '-alpha', 0.3, '-topmost', True)
            selection_window.configure(bg='black')
            selection_window.overrideredirect(True)
            
            canvas = tk.Canvas(selection_window, highlightthickness=0, bg='black')
            canvas.pack(fill=tk.BOTH, expand=True)
            
            start_x = start_y = 0
            rect_id = None
            region = None
            
            def on_mouse_press(event):
                nonlocal start_x, start_y, rect_id
                start_x, start_y = event.x, event.y
                if rect_id: canvas.delete(rect_id)
            
            def on_mouse_drag(event):
                nonlocal rect_id
                if rect_id: canvas.delete(rect_id)
                rect_id = canvas.create_rectangle(
                    start_x, start_y, event.x, event.y,
                    outline='red', width=2, fill='blue', stipple='gray50'
                )
            
            def on_mouse_release(event):
                nonlocal region
                x1, x2 = min(start_x, event.x), max(start_x, event.x)
                y1, y2 = min(start_y, event.y), max(start_y, event.y)
                region = (x1, y1, x2, y2)
                selection_window.destroy()
            
            canvas.bind('<Button-1>', on_mouse_press)
            canvas.bind('<B1-Motion>', on_mouse_drag)
            canvas.bind('<ButtonRelease-1>', on_mouse_release)
            selection_window.bind('<Escape>', lambda e: selection_window.destroy())
            
            selection_window.wait_window()
            return region
        except Exception as e:
            print(f"區域選擇錯誤: {e}")
            return None
        finally:
            self.is_selecting = False
    
    async def ocr_region(self, region: Tuple[int, int, int, int]) -> str:
        try:
            x1, y1, x2, y2 = region
            screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            
            if screenshot.mode != 'L': screenshot = screenshot.convert('L')
            screenshot = ImageEnhance.Contrast(screenshot).enhance(2.0)
            screenshot = ImageEnhance.Sharpness(screenshot).enhance(2.0)
            
            lang_mode = self.ocr_lang_var.get() if hasattr(self, 'ocr_lang_var') else 'jpn'
            direction_mode = self.ocr_direction_var.get() if hasattr(self, 'ocr_direction_var') else 'h'
            
            if direction_mode == 'v':
                actual_lang = 'jpn_vert' if 'jpn' in lang_mode else lang_mode
                psm_mode = 5
            else:
                actual_lang = lang_mode
                psm_mode = 6
            
            custom_config = f'--oem 3 --psm {psm_mode} -l {actual_lang}'
            text = await asyncio.to_thread(pytesseract.image_to_string, screenshot, config=custom_config)
            
            if not text: return ""

            if direction_mode == 'v':
                text = "".join(text.split())
            else:
                text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
            
            return text
        except pytesseract.TesseractNotFoundError:
            return "[錯誤: 未找到 Tesseract OCR，請確認安裝]"
        except Exception as e:
            return f"[OCR 錯誤: {str(e)}]"
    
    async def translate_text(self, text: str) -> str:
        #if not self.api_key: return "[錯誤: 未配置 Gemini API Key]"
        #if not text or not text.strip(): return "[無文字可翻譯]"
        #if aiohttp is None: return "[錯誤: aiohttp 未安裝]"
        
        try:
            prompt = f"請將以下文字翻譯成繁體中文（台灣習慣用語）。如果文字已經是繁體中文，請保持原樣。原文：\n{text}\n只輸出翻譯結果，不要添加任何說明。"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            

            available_models = []
            try:
                list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(list_url) as response:
                        if response.status == 200:
                            models_data = await response.json()
                            if 'models' in models_data:
                                available_models = [m['name'].split('/')[-1] for m in models_data['models'] 
                                                  if 'generateContent' in m.get('supportedGenerationMethods', [])]
            except Exception as e:
                pass
            
            # 構建要嘗試的模型列表（優先使用從 API 獲取的，否則使用預設列表）
            if available_models:
                models_to_try = [(api_v, model) for api_v in ["v1beta", "v1"] 
                               for model in available_models[:3]]  # 只嘗試前3個
            else:
                # 如果無法獲取模型列表，使用預設列表
                models_to_try = [
                    ("v1beta", "gemini-2.5-flash"),
                    ("v1beta", "gemini-1.5-flash-002"),
                    ("v1beta", "gemini-1.5-pro"),
                    ("v1beta", "gemini-pro"),
                    ("v1", "models/gemini-pro"),
                ]


            errors = [] # 收集所有錯誤訊息
            
            print("-" * 30)
            print("開始呼叫翻譯 API...")
            
            for api_version, model_name in models_to_try:
                url = f"https://generativelanguage.googleapis.com/{api_version}/models/{model_name}:generateContent?key={self.api_key}"
                
                try:
                    print(f"嘗試模型: {model_name} ...", end=" ")
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, json=payload) as response:
                            if response.status == 200:
                                print("成功！")
                                result = await response.json()
                                if 'candidates' in result and result['candidates']:
                                    return result['candidates'][0]['content']['parts'][0]['text'].strip()
                            else:
                                err_text = await response.text()
                                print(f"失敗 (Status: {response.status})")
                                # 記錄詳細錯誤以便除錯
                                err_msg = f"{model_name}: {response.status} - {err_text[:100]}"
                                errors.append(err_msg)
                                continue
                except Exception as e:
                    print(f"連線錯誤: {e}")
                    errors.append(f"{model_name}: {str(e)}")
                    continue
            
            # 如果程式跑到這裡，表示所有模型都失敗了
            print("所有模型均失敗。")
            print("-" * 30)
            return f"[翻譯失敗: 請查看黑色終端機視窗以獲取詳細錯誤]\n首個錯誤: {errors[0] if errors else '未知'}"
            
        except Exception as e:
            return f"[翻譯錯誤: {str(e)}]"
    
    async def process_region(self, region: Tuple[int, int, int, int]):
        try:
            if self.result_text:
                self.result_text.insert(tk.END, "正在處理...\n\n")
                self.root.update()
            
            original_text = await self.ocr_region(region)
            
            if not original_text or original_text.strip() == "":
                self.append_result("[未識別到文字]", is_original=True)
                self._add_separator()
                return

            if original_text.startswith("[錯誤"):
                self.append_result(original_text, is_original=True)
                if self.result_text:
                    self.result_text.insert(tk.END, "偵測到錯誤，已略過翻譯步驟。\n", 'translation')
                self._add_separator()
                return

            self.append_result(original_text, is_original=True)
            translated_text = await self.translate_text(original_text)
            self.append_result(translated_text, is_original=False)
            self._add_separator()
                
        except Exception as e:
            error_msg = f"[處理錯誤: {str(e)}]"
            if self.result_text:
                self.result_text.insert(tk.END, error_msg + "\n\n")
    
    def _add_separator(self):
        if self.result_text:
            self.result_text.insert(tk.END, "-" * 50 + "\n\n")
            self.result_text.see(tk.END)
            self.root.update()
    
    def on_hotkey_pressed(self):
        if self.is_selecting: return
        def process():
            region = self.select_region()
            if region:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.process_region(region))
                finally:
                    loop.close()
        threading.Thread(target=process, daemon=True).start()
    
    def start(self):
        self.create_gui()
        keyboard.add_hotkey(self.hotkey, self.on_hotkey_pressed)
        print(f"翻譯程式已啟動，快捷鍵: {self.hotkey.upper()}")
        print("請注意：如果翻譯失敗，詳細錯誤訊息會顯示在這個黑色視窗中。")
        try:
            self.root.mainloop()
        finally:
            keyboard.unhook_all()

if __name__ == '__main__':
    try:
        TranslationApp().start()
    except Exception as e:
        print(f"開啟程式時發生錯誤:{e}")