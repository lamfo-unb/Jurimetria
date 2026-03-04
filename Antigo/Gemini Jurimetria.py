import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox, font, simpledialog
import fitz                      # PyMuPDF
import google.generativeai as genai
from google.generativeai import types
import google.api_core.exceptions
import os
import threading
import time
import csv
import queue
import concurrent.futures
import json
import subprocess
import sys
import openpyxl                  # MODIFICADO: Nova importação para gerar arquivos Excel

# --- Configuração Inicial ---
API_KEY_ENV_VAR = "GOOGLE_API_KEY"
DEFAULT_GEMINI_MODEL = 'gemini-2.0-flash' 

AVAILABLE_GEMINI_MODELS = [ 
 'gemini-2.5-pro', 'gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-2.5-flash', 'gemini-2.5-flash-lite', 
 ]

SYSTEM_INSTRUCTION_JURIMETRICS = """
Você é uma IA assistente de jurimetria, especializada em analisar decisões judiciais e relatórios do sistema de justiça brasileiro. Sua tarefa é extrair dados estruturados do texto fornecido.

Com base *exclusivamente* no conteúdo do documento, extraia as seguintes informações:

1.  **Tribunal:** Identifique o tribunal que proferiu a decisão (ex: "TRF-4", "STJ", "TJ-SP", "TCU").
2.  **Tipo de Ação:** Identifique o tipo principal da ação ou do documento (ex: "Habeas Corpus", "Agravo de Instrumento", "Exceção de Suspeição", "Relatório de Auditoria").
3.  **Relator(es):** Extraia o nome do relator principal. Se houver mais de um juiz ou ministro mencionado de forma proeminente, liste-os.
4.  **Resultado:** Descreva de forma concisa o desfecho da decisão (ex: "Ordem denegada", "Recurso não provido", "Exceção de suspeição improcedente", "Ciência e arquivamento").
5.  **Resumo Jurimétrico:** Crie um resumo de 1 a 2 frases com o insight mais importante do documento do ponto de vista jurimétrico. Foque no argumento central que levou à decisão ou no principal dado quantitativo apresentado.

Sua resposta DEVE ser um objeto JSON com exatamente os seguintes campos:
- "tribunal": string
- "tipo_acao": string
- "relator": string
- "resultado": string
- "resumo_jurimetrico": string

Se alguma informação não puder ser encontrada, preencha o campo correspondente com "Não identificado".
"""

# --- Configurações (sem alterações) ---
MAX_RETRIES_PER_CALL = 3
INITIAL_BACKOFF = 2
MAX_BACKOFF = 16
DEFAULT_MAX_WORKERS_BATCH = 5

class OperationCancelledError(Exception):
    pass

# ... (Funções gemini_api_call_with_retry, get_text_from_file, analyze_document_with_gemini permanecem iguais) ...
def gemini_api_call_with_retry(api_function_call, cancel_event, status_callback):
    retries = 0
    backoff = INITIAL_BACKOFF
    retryable_exceptions = (
        google.api_core.exceptions.DeadlineExceeded,
        google.api_core.exceptions.ServiceUnavailable,
        google.api_core.exceptions.InternalServerError,
        google.api_core.exceptions.TooManyRequests,
    )
    while retries <= MAX_RETRIES_PER_CALL:
        if cancel_event.is_set():
            raise OperationCancelledError("Operation cancelled during Gemini retry.")
        try:
            return api_function_call()
        except retryable_exceptions as e:
            retries += 1
            err_msg = f"API Error ({type(e).__name__}): {e}. "
            if retries > MAX_RETRIES_PER_CALL:
                status_callback(f"  {err_msg}Max retries exceeded.")
                raise
            status_callback(f"  {err_msg}Retrying ({retries}/{MAX_RETRIES_PER_CALL}) in {backoff}s...")
            total_loops = int(backoff * 10)
            for _ in range(total_loops):
                if cancel_event.is_set():
                    raise OperationCancelledError("Operation cancelled while waiting for retry.")
                time.sleep(0.1)
            backoff = min(backoff * 2, MAX_BACKOFF)
        except Exception as e:
            status_callback(f"  Unexpected API error (non-retryable): {type(e).__name__} - {e}")
            raise
    return None

def get_text_from_file(file_path, password_request_callback, status_callback, cancel_event):
    filename = os.path.basename(file_path)
    status_callback(f"  Extracting text from: {filename}")
    
    if filename.lower().endswith(".pdf"):
        doc = None
        try:
            doc = fitz.open(file_path)
            if doc.is_encrypted:
                status_callback(f"  PDF '{filename}' is encrypted. Asking for password…")
                password = password_request_callback(filename)
                if cancel_event.is_set() or password is None:
                    raise OperationCancelledError(f"Password entry canceled/skipped for {filename}")
                if not doc.authenticate(password):
                    status_callback(f"  Incorrect password for '{filename}'. Skipping.")
                    return None
            
            full_text = ""
            for page_idx in range(len(doc)):
                if cancel_event.is_set():
                    raise OperationCancelledError(f"Extraction canceled for {filename}")
                page = doc.load_page(page_idx)
                full_text += page.get_text("text") + "\n"
            status_callback(f"  Text extracted successfully from '{filename}'.")
            return full_text
        finally:
            if doc:
                doc.close()
                
    elif filename.lower().endswith(".txt"):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                full_text = f.read()
            status_callback(f"  Text read successfully from '{filename}'.")
            return full_text
        except Exception as e:
            status_callback(f"  Error reading TXT file '{filename}': {e}")
            return None
    else:
        status_callback(f"  Unsupported file type for '{filename}'. Skipping.")
        return None

def analyze_document_with_gemini(model, full_text_content, filename, cancel_event, status_callback):
    status_callback(f"  Analyzing '{filename}' with Gemini AI…")
    if not full_text_content:
        return {"tribunal": "N/A", "tipo_acao": "N/A", "relator": "N/A", "resultado": "Erro", "resumo_jurimetrico": "Document text is empty or could not be extracted."}

    generation_config = types.GenerationConfig(
        response_mime_type="application/json",
        temperature=0.1
    )

    try:
        def api_call():
            return model.generate_content(
                contents=[full_text_content],
                generation_config=generation_config
            )

        response = gemini_api_call_with_retry(api_call, cancel_event, status_callback)

        if cancel_event.is_set():
            raise OperationCancelledError(f"AI analysis canceled for {filename}")
        
        json_text = response.candidates[0].content.parts[0].text
        ai_result = json.loads(json_text)
        
        status_callback(f"  Successfully analyzed '{filename}'.")
        return ai_result
    
    except OperationCancelledError:
        status_callback(f"  AI analysis canceled for '{filename}'")
        raise
    except Exception as e:
        status_callback(f"  Error during AI analysis for '{filename}': {type(e).__name__} - {e}")
        return {"tribunal": "N/A", "tipo_acao": "N/A", "relator": "N/A", "resultado": "Erro", "resumo_jurimetrico": f"Error during AI analysis: {e}"}


def generate_csv_report(results_list, output_csv_path, status_callback):
    status_callback(f"Generating Jurimetrics CSV report at: {output_csv_path}")
    try:
        with open(output_csv_path, "w", newline="", encoding="utf-8-sig") as csvfile:
            fieldnames = ["Filename", "Tribunal", "Tipo de Ação", "Relator", "Resultado", "Resumo Jurimétrico"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for result in results_list:
                writer.writerow({
                    "Filename": result.get("filename", "N/A"),
                    "Tribunal": result.get("tribunal", "N/A"),
                    "Tipo de Ação": result.get("tipo_acao", "N/A"),
                    "Relator": result.get("relator", "N/A"),
                    "Resultado": result.get("resultado", "N/A"),
                    "Resumo Jurimétrico": result.get("resumo_jurimetrico", "N/A"),
                })
        status_callback(f"CSV report generated successfully: {output_csv_path}")
        return True
    except Exception as e:
        status_callback(f"Error generating CSV: {e}")
        return False

# MODIFICADO: Nova função para gerar o relatório em XLSX
def generate_xlsx_report(results_list, output_xlsx_path, status_callback):
    """
    Gera um relatório XLSX com os resultados da análise.
    """
    status_callback(f"Generating Jurimetrics XLSX report at: {output_xlsx_path}")
    try:
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Jurimetrics Analysis"

        # Escreve o cabeçalho
        headers = ["Filename", "Tribunal", "Tipo de Ação", "Relator", "Resultado", "Resumo Jurimétrico"]
        sheet.append(headers)

        # Formata o cabeçalho
        for cell in sheet[1]:
            cell.font = openpyxl.styles.Font(bold=True)

        # Escreve os dados
        for result in results_list:
            row_data = [
                result.get("filename", "N/A"),
                result.get("tribunal", "N/A"),
                result.get("tipo_acao", "N/A"),
                result.get("relator", "N/A"),
                result.get("resultado", "N/A"),
                result.get("resumo_jurimetrico", "N/A")
            ]
            sheet.append(row_data)

        # Auto-ajusta a largura das colunas
        for column_cells in sheet.columns:
            length = max(len(str(cell.value)) for cell in column_cells)
            sheet.column_dimensions[column_cells[0].column_letter].width = length + 2

        workbook.save(output_xlsx_path)
        status_callback(f"XLSX report generated successfully: {output_xlsx_path}")
        return True
    except Exception as e:
        status_callback(f"Error generating XLSX report: {e}")
        return False


class JurimetricsApp:
    # ... (O __init__ e a maior parte da classe permanecem os mesmos) ...
    def __init__(self, root_window):
        self.root = root_window
        self.root.title("Jurimetrics AI Agent (Gemini & TXT/PDF Files)")
        self.root.geometry("900x750")
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.root.configure(bg="#f0f0f0")

        self.cancel_event = threading.Event()
        self.processing_thread = None
        self.password_queue = queue.Queue()
        self.current_pdf_for_password = None

        self.label_font = font.Font(family="Segoe UI", size=10)
        self.button_font = font.Font(family="Segoe UI", size=10, weight="bold")
        self.text_font = font.Font(family="Consolas", size=9)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", background="#f0f0f0", foreground="#333333", font=self.label_font)
        style.configure("TButton", font=self.button_font, padding=5)
        style.map("TButton", background=[("active", "#e0e0e0"), ("!disabled", "#f0f0f0"), ("pressed", "#d0d0d0"), ("disabled", "#cccccc")], foreground=[("disabled", "#888888")])
        style.configure("TEntry", font=self.text_font, padding=3)
        style.configure("TFrame", background="#f0f0f0")
        style.configure("Horizontal.TProgressbar", troughcolor="#e0e0e0", background="#0078d4", thickness=20)
        style.configure("TCombobox", font=self.text_font, padding=3)
        self.root.option_add("*TCombobox*Listbox*Font", self.text_font)

        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(expand=True, fill=tk.BOTH)

        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(input_frame, text="Process:").pack(side=tk.LEFT, padx=(0, 5))
        self.process_mode_var = tk.StringVar(value="folder")
        self.radio_single = ttk.Radiobutton(input_frame, text="Single File", variable=self.process_mode_var, value="single", command=self.toggle_input_mode)
        self.radio_single.pack(side=tk.LEFT, padx=5)
        self.radio_folder = ttk.Radiobutton(input_frame, text="Folder (Batch)", variable=self.process_mode_var, value="folder", command=self.toggle_input_mode)
        self.radio_folder.pack(side=tk.LEFT, padx=5)

        self.path_input_frame = ttk.Frame(main_frame)
        self.path_input_frame.pack(fill=tk.X, pady=(0,10))
        self.path_label = ttk.Label(self.path_input_frame, text="File/Folder Path:")
        self.path_label.pack(side=tk.LEFT, padx=(0,5))
        self.path_var = tk.StringVar()
        self.path_entry = ttk.Entry(self.path_input_frame, textvariable=self.path_var, width=70)
        self.path_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,5))
        self.browse_btn = ttk.Button(self.path_input_frame, text="Browse...", command=self.select_path)
        self.browse_btn.pack(side=tk.LEFT, padx=(5,0))

        settings_frame = ttk.Frame(main_frame)
        settings_frame.pack(fill=tk.X, pady=5)
        ttk.Label(settings_frame, text="Gemini Model:").pack(side=tk.LEFT, padx=(0,5))
        self.model_var = tk.StringVar(value=DEFAULT_GEMINI_MODEL)
        self.model_cb = ttk.Combobox(settings_frame, textvariable=self.model_var, values=AVAILABLE_GEMINI_MODELS, state="readonly", width=30)
        self.model_cb.pack(side=tk.LEFT, padx=(0,10))
        ttk.Label(settings_frame, text="Batch Workers:").pack(side=tk.LEFT, padx=(5,5))
        self.workers_var = tk.StringVar(value=str(DEFAULT_MAX_WORKERS_BATCH))
        self.workers_entry = ttk.Entry(settings_frame, textvariable=self.workers_var, width=5)
        self.workers_entry.pack(side=tk.LEFT)

        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=10)
        self.start_btn = ttk.Button(action_frame, text="Start Jurimetrics Analysis", command=self.start_processing, style="Accent.TButton")
        style.configure("Accent.TButton", foreground="white", background="#0078d4")
        style.map("Accent.TButton", background=[("active", "#005a9e"), ("pressed", "#004c87"), ("disabled", "#b0b0b0")])
        self.start_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,5))

        self.cancel_btn = ttk.Button(action_frame, text="Cancel", command=self.request_cancellation, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)
        self.clear_log_btn = ttk.Button(action_frame, text="Clear Log", command=self.clear_log)
        self.clear_log_btn.pack(side=tk.LEFT, padx=(5,0))

        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(5,0))
        self.progress_label_var = tk.StringVar(value="Ready.")
        self.progress_label = ttk.Label(progress_frame, textvariable=self.progress_label_var, anchor=tk.W)
        self.progress_label.pack(fill=tk.X)
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100, mode="determinate", style="Horizontal.TProgressbar")
        self.progress_bar.pack(fill=tk.X, pady=(2,10))

        log_label = ttk.Label(main_frame, text="Processing Log:")
        log_label.pack(anchor=tk.W, pady=(5,2))
        self.status_text = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, height=15, font=self.text_font, bg="#ffffff", fg="#333333", relief=tk.SUNKEN, bd=1)
        self.status_text.pack(expand=True, fill=tk.BOTH, pady=5)
        self.status_text.configure(state="disabled")

        self.toggle_input_mode()
        self.set_controls_state(True)

    def _on_closing(self):
        if self.processing_thread and self.processing_thread.is_alive():
            if messagebox.askokcancel("Quit", "Analysis in progress. Are you sure you want to quit?", parent=self.root):
                self.request_cancellation(force_cancel=True)
                self.root.after(500, self._check_thread_and_destroy)
            else:
                return
        else:
            self.root.destroy()
    
    def _check_thread_and_destroy(self):
        if self.processing_thread and self.processing_thread.is_alive():
            self.update_status("Force quitting…")
        self.root.destroy()

    def toggle_input_mode(self):
        mode = self.process_mode_var.get()
        busy = bool(self.processing_thread and self.processing_thread.is_alive())
        if mode == "single":
            self.path_label.config(text="File Path:")
            self.workers_entry.config(state=tk.DISABLED)
        else:
            self.path_label.config(text="Folder Path:")
            self.workers_entry.config(state=tk.NORMAL if not busy else tk.DISABLED)
        self.path_var.set("")

    def select_path(self):
        if self.processing_thread and self.processing_thread.is_alive():
            return
        mode = self.process_mode_var.get()
        if mode == "single":
            filepath = filedialog.askopenfilename(
                title="Select File", filetypes=(("Text and PDF files", "*.txt *.pdf"), ("All files", "*.*")), parent=self.root
            )
            if filepath:
                self.path_var.set(filepath)
        else:
            folderpath = filedialog.askdirectory(title="Select Folder", parent=self.root)
            if folderpath:
                self.path_var.set(folderpath)

    def update_status(self, msg: str):
        def append_message():
            if not hasattr(self.root, "winfo_exists") or not self.root.winfo_exists(): return
            try:
                self.status_text.configure(state="normal")
                ts = time.strftime("%H:%M:%S")
                self.status_text.insert(tk.END, f"[{ts}] {msg}\n")
                self.status_text.configure(state="disabled")
                self.status_text.see(tk.END)
            except tk.TclError: pass
        if hasattr(self.root, "winfo_exists") and self.root.winfo_exists():
            self.root.after(0, append_message)

    def update_progress_bar(self, current_val: int, total_val: int, phase_text: str = "Processing..."):
        def update():
            if not hasattr(self.root, "winfo_exists") or not self.root.winfo_exists(): return
            try:
                self.progress_var.set(current_val)
                self.progress_bar["maximum"] = total_val if total_val > 0 else 100
                disp = phase_text if len(phase_text) <= 60 else phase_text[:57] + "..."
                self.progress_label_var.set(f"{disp} ({current_val}/{total_val})")
            except tk.TclError: pass
        if hasattr(self.root, "winfo_exists") and self.root.winfo_exists():
            self.root.after(0, update)
    
    def request_password_from_gui(self, pdf_filename: str):
        self.current_pdf_for_password = pdf_filename
        def ask_password():
            pwd = simpledialog.askstring("PDF Password Required", f"Enter password for '{pdf_filename}':", parent=self.root, show="*")
            self.password_queue.put(pwd)
        self.root.after(0, ask_password)
        try:
            password = self.password_queue.get(timeout=600)
            return password
        except queue.Empty:
            return None

    def clear_log(self):
        try:
            self.status_text.configure(state="normal")
            self.status_text.delete("1.0", tk.END)
            self.status_text.configure(state="disabled")
            self.update_status("Log cleared by user.")
        except tk.TclError: pass

    def request_cancellation(self, force_cancel: bool = False):
        if self.processing_thread and self.processing_thread.is_alive():
            if force_cancel or messagebox.askyesno("Confirm Cancellation", "Are you sure you want to cancel?", parent=self.root):
                self.cancel_event.set()
                self.update_status("Cancellation requested...")
                self.cancel_btn.config(state=tk.DISABLED, text="Cancelling…")

    def set_controls_state(self, active: bool):
        btn_state = tk.NORMAL if active else tk.DISABLED
        entry_state = "normal" if active else "readonly"
        self.start_btn.config(state=btn_state)
        self.browse_btn.config(state=btn_state)
        self.path_entry.config(state=entry_state)
        self.model_cb.config(state="readonly" if active else "disabled")
        radio_state = tk.NORMAL if active else tk.DISABLED
        self.radio_single.config(state=radio_state)
        self.radio_folder.config(state=radio_state)
        if self.process_mode_var.get() == "folder" and active:
            self.workers_entry.config(state="normal")
        else:
            self.workers_entry.config(state="disabled")
        self.cancel_btn.config(state=tk.NORMAL if not active else tk.DISABLED, text="Cancel")

    def processing_complete(self, success: bool, message: str, csv_path: str = None):
        def final_actions():
            if not hasattr(self.root, "winfo_exists") or not self.root.winfo_exists(): return
            self.set_controls_state(True)
            self.progress_label_var.set("Operation Completed!" if success else "Operation Failed/Cancelled.")
            if success:
                if csv_path: # O caminho passado é o do CSV, o XLSX tem o mesmo nome base
                    folder = os.path.dirname(csv_path)
                    if messagebox.askyesno("Analysis Complete", f"{message}\n\nReports (CSV and XLSX) saved in:\n{folder}\n\nOpen folder?", parent=self.root):
                        try:
                            if sys.platform == "win32": subprocess.run(["explorer", folder], check=True)
                            elif sys.platform == "darwin": subprocess.run(["open", folder], check=True)
                            else: subprocess.run(["xdg-open", folder], check=True)
                        except Exception as e: self.update_status(f"Could not open folder: {e}")
                else:
                    messagebox.showinfo("Analysis Complete", message, parent=self.root)
            else:
                messagebox.showerror("Operation Ended", message, parent=self.root)
            self.update_status("-------------------- Ready for new analysis --------------------")
            self.cancel_event.clear()
            self.processing_thread = None
        if hasattr(self.root, "winfo_exists") and self.root.winfo_exists():
            self.root.after(0, final_actions)

    def start_processing(self):
        input_path = self.path_var.get().strip()
        if not input_path:
            messagebox.showerror("Input Error", "Please select a file or folder.", parent=self.root)
            return
        
        # ... (restante da lógica de validação) ...
        num_workers = int(self.workers_var.get())

        self.update_status(f"Starting analysis: {input_path}")
        self.cancel_event.clear()
        self.set_controls_state(False)
        self.progress_var.set(0)
        
        self.processing_thread = threading.Thread(
            target=process_documents_thread,
            args=(
                input_path, self.process_mode_var.get(), self.model_var.get(),
                num_workers, self.cancel_event, self.update_status,
                self.processing_complete, self.request_password_from_gui, self.update_progress_bar
            ),
            daemon=True,
        )
        self.processing_thread.start()

def process_documents_thread(
    input_path: str, mode: str, selected_model: str, num_workers: int,
    cancel_event: threading.Event, status_callback: callable, completion_callback: callable,
    password_request_callback: callable, progress_callback: callable
):
    api_key = os.environ.get(API_KEY_ENV_VAR)
    if not api_key:
        completion_callback(False, f"Error: Environment variable '{API_KEY_ENV_VAR}' not set.")
        return

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=selected_model,
            system_instruction=SYSTEM_INSTRUCTION_JURIMETRICS
        )
        status_callback(f"Gemini AI Model '{selected_model}' initialized for jurimetrics.")
    except Exception as e:
        completion_callback(False, f"Error initializing Gemini: {e}")
        return

    files_to_process = []
    if mode == "single":
        files_to_process.append(input_path)
    else:
        for fname in os.listdir(input_path):
            if fname.lower().endswith((".pdf", ".txt")):
                files_to_process.append(os.path.join(input_path, fname))
        if not files_to_process:
            completion_callback(True, "No PDF or TXT files found in the folder.")
            return
        status_callback(f"Found {len(files_to_process)} file(s) in folder.")

    total_files = len(files_to_process)
    processed_count = 0

    def process_single(file_path: str):
        nonlocal processed_count
        if cancel_event.is_set(): raise OperationCancelledError("Cancelled before processing.")
        
        filename = os.path.basename(file_path)
        progress_callback(processed_count, total_files, f"Starting: {filename}")
        
        try:
            text = get_text_from_file(file_path, password_request_callback, status_callback, cancel_event)
            if text is None:
                return {"filename": filename, "resultado": "Erro", "resumo_jurimetrico": "Failed to extract text."}
            ai_res = analyze_document_with_gemini(model, text, filename, cancel_event, status_callback)
            return {"filename": filename, **ai_res}
        except Exception as e:
            return {"filename": filename, "resultado": "Erro", "resumo_jurimetrico": f"Unexpected error: {e}"}

    try:
        results_for_csv = []
        if mode == "single":
            result = process_single(files_to_process[0])
            msg = f"Analysis for '{result['filename']}':\n\n"
            for key, value in result.items():
                if key != 'filename':
                    msg += f"  - {key.replace('_', ' ').title()}: {value}\n"
            completion_callback(True, msg)
        else: # Batch
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                future_to_file = {executor.submit(process_single, path): path for path in files_to_process}
                for future in concurrent.futures.as_completed(future_to_file):
                    try:
                        res = future.result()
                        if res: results_for_csv.append(res)
                    except Exception as exc:
                        filename = os.path.basename(future_to_file[future])
                        results_for_csv.append({"filename": filename, "resultado": "Erro Fatal", "resumo_jurimetrico": str(exc)})
                    finally:
                        processed_count += 1
                        progress_callback(processed_count, total_files, f"Batch progress")
            
            if cancel_event.is_set():
                raise OperationCancelledError("Batch processing cancelled.")
            
            if results_for_csv:
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                report_basename = f"jurimetrics_results_{timestamp}"
                output_dir = os.path.dirname(input_path) 
                
                # Gera ambos os relatórios
                final_csv = os.path.join(output_dir, f"{report_basename}.csv")
                final_xlsx = os.path.join(output_dir, f"{report_basename}.xlsx")
                
                csv_ok = generate_csv_report(results_for_csv, final_csv, status_callback)
                xlsx_ok = generate_xlsx_report(results_for_csv, final_xlsx, status_callback) # MODIFICADO
                
                if csv_ok and xlsx_ok:
                    completion_callback(True, f"Batch analysis complete for {len(results_for_csv)} files.", csv_path=final_csv)
                else:
                    completion_callback(False, "Batch complete, but failed to generate one or more reports.")

    except OperationCancelledError as e:
        completion_callback(False, f"Operation Cancelled: {e}")
    except Exception as e:
        completion_callback(False, f"Critical error in processing thread: {e}")


if __name__ == "__main__":
    api_key_present = bool(os.environ.get(API_KEY_ENV_VAR))
    root = tk.Tk()
    if not api_key_present:
        messagebox.showwarning("API Key Missing", f"Environment variable '{API_KEY_ENV_VAR}' is not set.")
    app = JurimetricsApp(root)
    root.mainloop()
