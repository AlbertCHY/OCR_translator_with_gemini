# Local LLM Screen Translator（本地端 AI 螢幕翻譯與文字擷取工具）

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)
![LLM](https://img.shields.io/badge/LLM-Ollama-black)
![OCR](https://img.shields.io/badge/OCR-RapidOCR%20(ONNX)-green)

一款完全在本地端運行的 Windows 桌面工具，結合 **RapidOCR (ONNX Runtime)** 與 **Ollama 本地大型語言模型**，提供「螢幕框選翻譯」、「純文字 OCR 擷取」與「內建 AI 串流對話」三大功能。無需上傳截圖或文字至雲端 API，兼顧隱私安全與離線可用性。

---

## ✨ 主要功能

- **螢幕框選翻譯 (`Ctrl + Shift + T`)**
  - 按下全域快捷鍵即可進入半透明全螢幕框選模式，自動進行 OCR 文字辨識並交由本地 Ollama 模型翻譯成繁體中文（保留專有名詞原文）。
- **純文字 OCR 擷取 (`Ctrl + Shift + O`)**
  - 只進行文字辨識並自動複製結果至剪貼簿，方便日常文書處理與資料摘錄。
- **內建 AI 串流對話**
  - 視窗底部提供即時輸入框，直接與本地 LLM 互動。
  - 採用 **Streaming 串流輸出** (`stream=True`)，即時逐字顯示模型回應。
  - 實作 **滑動視窗 (Sliding Window)** 對話記憶機制（預設保留最近 10 回合對話），兼顧上下文連貫與 Prompt 長度控制，並可一鍵「忘記對話」。
- **實用細節與防呆設計**
  - **自動合併斷行**：可依需求切換是否自動將換行合併為空白（適合翻譯或複製多行文章）。
  - **高 DPI 縮放相容**：啟用 Windows `SetProcessDpiAwareness`，避免螢幕縮放比例造成截圖座標偏移。
  - **Ollama 啟動防呆檢查**：程式啟動時自動於背景檢查 Ollama 服務是否運行及指定模型是否已下載，異常時主動彈窗提示。
  - **處理狀態回饋**：辨識或生成回應期間自動將滑鼠游標切換為等待圖示 (`watch`)。
  - **視窗置頂**：主視窗預設保持最上層，方便一邊閱讀文件一邊對照翻譯。

---

## 🛠️ 系統需求

- **作業系統**：Windows 10 / 11
- **Python**：建議 Python 3.10 以上
- **Ollama**：需先安裝並啟動 [Ollama](https://ollama.com/)

---

## 🚀 快速開始

### 1. 安裝並準備 Ollama 模型

安裝 Ollama 後，依本機硬體效能拉取適合的模型（例如輕量版 `gemma3:1b` / `gemma3:4b`，或效能較佳的電腦可使用 `gemma3:12b`）：

```bash
ollama pull gemma3:4b
```

確認 Ollama 服務已啟動（預設監聽 `http://localhost:11434/`）。

### 2. 下載專案與安裝相依套件

```bash
git clone https://github.com/AlbertCHY/translator_by_cursor.git
cd translator_by_cursor
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 準備 RapidOCR 模型檔案

本專案使用較新的 PP-OCRv5 ONNX 模型以提升中英文辨識準確度。由於模型檔案較大未納入版本控制，請在專案根目錄建立 `model/` 資料夾，並放入以下兩個模型檔（可從 RapidOCR / PaddleOCR ONNX 相關開源資源下載）：

```text
model/
├── ch_PP-OCRv5_mobile_det.onnx
└── ch_PP-OCRv5_rec_mobile_infer.onnx
```

> 若想改用其他 ONNX 模型，可調整 `translator_local.py` 頂端的 `DEFAULT_OCR_DIR_DET` 與 `DEFAULT_OCR_DIR_REC`。

### 4. 設定 `config.json`

複製專案內的範例檔 [config.example.json](config.example.json) 並重新命名為 `config.json`：

```bash
copy config.example.json config.json
```

`config.json` 範例內容如下：

```json
{
  "ollama_url": "http://localhost:11434/",
  "model_name": "gemma3:4b",
  "hotkey_translate": "ctrl+shift+t",
  "hotkey_ocr": "ctrl+shift+o",
  "translate_prompt": "將以下內容翻譯成繁體中文。專有名詞要保留原文。直接輸出翻譯結果，不要包含任何解釋：",
  "chat_prompt": "你是一個繁體中文的 AI 助理，回答請簡潔精確。"
}
```

| 參數 | 說明 | 預設值 |
| :--- | :--- | :--- |
| `ollama_url` | Ollama API 服務位址 | `http://localhost:11434/` |
| `model_name` | 使用的本地模型名稱（需與 `ollama list` 相符） | `gemma3:1b` |
| `hotkey_translate` | 框選翻譯的全域快捷鍵 | `ctrl+shift+t` |
| `hotkey_ocr` | 純文字擷取的全域快捷鍵 | `ctrl+shift+o` |
| `translate_prompt` | 翻譯模式的前置提示詞 | 繁體中文翻譯提示 |
| `chat_prompt` | 對話模式的 System Prompt | 繁體中文簡潔助理提示 |

### 5. 執行程式

```bash
python translator_local.py
```

---

## 🖱️ 操作說明

| 功能 | 快捷鍵 / 操作方式 | 說明 |
| :--- | :--- | :--- |
| **擷取並翻譯** | `Ctrl + Shift + T` 或點擊按鈕 | 拖曳框選螢幕區域（按 `Esc` 取消），辨識後呼叫 LLM 翻譯 |
| **擷取並複製** | `Ctrl + Shift + O` 或點擊按鈕 | 拖曳框選螢幕區域，辨識完成後自動複製純文字到剪貼簿 |
| **AI 對話** | 底部「問 AI」輸入框按 `Enter` | 與本地模型進行多輪串流對話 |
| **自動合併斷行** | 勾選介面核取方塊 | 開啟時將 OCR 結果中的換行轉為空白，適合段落文章 |
| **忘記對話** | 點擊「忘記對話」按鈕 | 清除 LLM 對話歷史紀錄，重新開始上下文 |
| **清除畫面** | 點擊「清除畫面」按鈕 | 清空顯示區域的文字紀錄 |

---

## 📦 打包成 Windows EXE 執行檔

可使用 `PyInstaller` 將程式與 `model/` 資料夾打包為獨立目錄版執行檔：

```bash
pip install pyinstaller
pyinstaller --noconsole --name Local_LLM_Translator --add-data "model;model" --collect-all rapidocr_onnxruntime translator_local.py
```

打包完成後，請將 `config.json` 複製到 `dist/Local_LLM_Translator/`（與 `Local_LLM_Translator.exe` 同層目錄）即可執行。

> 程式內部已透過 `sys.frozen` 與 `sys._MEIPASS` 區分打包環境：OCR 模型會由打包目錄讀取，而 `config.json` 會強制由 `.exe` 旁讀取，方便隨時修改模型名稱與提示詞而不需重新打包。

---

## 📁 專案結構

```text
.
├── translator_local.py   # 主程式（V4：RapidOCR + Ollama + 串流對話）
├── main.py               # 早期版本留存（Tesseract + 雲端 API）
├── config.example.json   # 設定檔範例（請複製為 config.json 後使用）
├── config.json           # 本機使用者設定檔（已列入 .gitignore，不納入版控）
├── requirements.txt      # Python 套件清單
└── model/                # RapidOCR ONNX 模型資料夾（需自行放置）
```

---

## 📝 開發歷程與技術選型紀錄

這個專案從最初的原型到可獨立打包執行的本地工具，經歷了多次技術棧調整與踩坑整理：

1. **V1｜原型建立與架構瘦身**
   - 初期透過 Cursor 產生第一版 GUI 與程式，但因虛擬環境套件找不到、反覆修補導致程式碼日趨臃腫；後續轉由 Gemini 協助釐清環境依賴並進行大幅瘦身。
   - 最初採用 Tesseract OCR（搭配額外語言包）與 Gemini API；因評估 Docker 容器不適合存取本機螢幕與硬體介面，改以打包成 Windows `.exe` 順利於本機運行。
2. **V2｜從雲端 API 轉向本地 Ollama**
   - 將 Gemini API 全面替換為 **Ollama** 本地推論，讓不同硬體環境可彈性切換模型（例如公司電腦跑輕量模型，家用電腦則可使用 `gemma3:12b`），同時導入 Git 進行版本控制。
3. **V3｜OCR 引擎轉換的踩坑與落地**
   - 嘗試將 Tesseract 替換為 **PaddleOCR** 時，接連遇到新版 API 函式/參數不相容、修正後辨識結果持續輸出固定亂碼，以及降版後在自動下載模型階段遭遇 SSL 握手失敗等問題，最終果斷放棄。
   - 改採輕量且以 ONNX Runtime 運行的 **RapidOCR** 後順利整合，並手動換用較新的 **PP-OCRv5** 模型顯著提升辨識品質。
4. **V4｜功能擴充、體驗優化與發布**
   - 進行程式碼重構（拆分 `AppConfig`、`OCRService`、`OllamaService` 與 UI 層），並抽出全域預設常數提升可維護性。
   - 新增「純文字 OCR 複製」模式，以及支援 **Sliding Window 記憶管理**與 **Streaming 串流顯示**的本地 AI 對話功能。
   - 強化桌面端體驗：補上高 DPI 縮放容忍、Ollama 服務與模型防呆檢查、讀取中游標回饋，並解決 PyInstaller 打包後的工作目錄與外部設定檔路徑問題，最後透過 Pull Request 合併與建立 Git Tag (`v1.0`) 完成版本管理。
