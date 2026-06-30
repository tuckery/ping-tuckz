import queue
import threading
from collections import deque
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

import ping_tuckz_core as core


GRAPH_WINDOW_SECONDS = 300


class PingTuckzApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Ping Tuckz")
        self.root.geometry("980x680")
        self.root.minsize(760, 520)

        self.events = queue.Queue()
        self.samples = deque()
        self.worker = None
        self.stop_event = None
        self.close_after_stop = False

        self.target_var = tk.StringVar(value=core.DEFAULT_TARGET)
        self.status_var = tk.StringVar(value="Stopped")
        self.latest_var = tk.StringVar(value="Latest: -")
        self.files_var = tk.StringVar(value="Results: -")

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self.process_events)

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="Target").pack(side=tk.LEFT)
        self.target_entry = ttk.Entry(controls, textvariable=self.target_var, width=32)
        self.target_entry.pack(side=tk.LEFT, padx=(6, 12))

        self.start_button = ttk.Button(controls, text="Start", command=self.start)
        self.start_button.pack(side=tk.LEFT)
        self.stop_button = ttk.Button(controls, text="Stop", command=self.stop, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=(6, 12))

        ttk.Label(controls, textvariable=self.status_var).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(controls, textvariable=self.latest_var).pack(side=tk.LEFT)

        self.graph = tk.Canvas(outer, height=220, bg="#111827", highlightthickness=1, highlightbackground="#374151")
        self.graph.pack(fill=tk.X, pady=(10, 8))
        self.graph.bind("<Configure>", lambda _event: self.draw_graph())

        ttk.Label(outer, textvariable=self.files_var).pack(fill=tk.X, anchor=tk.W)

        self.log = ScrolledText(outer, height=18, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 10))
        self.log.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.log.tag_configure("NORMAL", foreground="#374151")
        self.log.tag_configure("MEDIUM", foreground="#b45309")
        self.log.tag_configure("HIGH", foreground="#b91c1c")
        self.log.tag_configure("TIMEOUT", foreground="#dc2626")
        self.log.tag_configure("INFO", foreground="#1f2937")
        self.log.tag_configure("ERROR", foreground="#991b1b")

    def start(self):
        if self.worker and self.worker.is_alive():
            return

        target = self.target_var.get().strip() or core.DEFAULT_TARGET
        self.target_var.set(target)
        self.stop_event = threading.Event()
        self.close_after_stop = False
        self.samples.clear()
        self.draw_graph()

        self.status_var.set("Running")
        self.latest_var.set("Latest: -")
        self.target_entry.configure(state=tk.DISABLED)
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.append_log(f"Starting monitor for {target}", "INFO")

        self.worker = threading.Thread(target=self._run_worker, args=(target,), daemon=True)
        self.worker.start()

    def stop(self):
        if not self.worker or not self.worker.is_alive():
            return
        self.status_var.set("Finalizing...")
        self.stop_button.configure(state=tk.DISABLED)
        self.append_log("Stopping monitor and finalizing results...", "INFO")
        self.stop_event.set()

    def on_close(self):
        if self.worker and self.worker.is_alive():
            self.close_after_stop = True
            self.stop()
            return
        self.root.destroy()

    def _run_worker(self, target):
        try:
            core.run_monitor(
                target=target,
                stop_event=self.stop_event,
                on_log=lambda **event: self.events.put(("log", event)),
                on_sample=lambda **event: self.events.put(("sample", event)),
                on_files_changed=lambda **event: self.events.put(("files", event)),
                on_error=lambda **event: self.events.put(("error", event)),
                on_stopped=lambda **event: self.events.put(("stopped", event)),
                refresh_html=False,
            )
        except Exception as exc:
            self.events.put(("error", {"message": str(exc)}))
            self.events.put(("stopped", {"txt_path": None, "html_path": None}))

    def process_events(self):
        while True:
            try:
                event_type, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if event_type == "log":
                self.handle_log(payload)
            elif event_type == "sample":
                self.handle_sample(payload)
            elif event_type == "files":
                self.handle_files(payload)
            elif event_type == "error":
                self.append_log(f"Error: {payload.get('message', '')}", "ERROR")
            elif event_type == "stopped":
                self.handle_stopped(payload)

        self.root.after(100, self.process_events)

    def handle_log(self, payload):
        status = payload.get("status") or "INFO"
        message = payload.get("message", "")
        self.append_log(message, status)

    def handle_sample(self, payload):
        timestamp = payload.get("timestamp") or datetime.now()
        latency = payload.get("latency")
        self.samples.append((timestamp, latency))
        cutoff = timestamp - timedelta(seconds=GRAPH_WINDOW_SECONDS)
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.popleft()

        self.latest_var.set("Latest: timeout" if latency is None else f"Latest: {latency} ms")
        self.draw_graph()

    def handle_files(self, payload):
        txt_path = payload.get("txt_path")
        html_path = payload.get("html_path")
        if txt_path and html_path:
            self.files_var.set(f"Results: {txt_path} / {html_path}")

    def handle_stopped(self, payload):
        self.status_var.set("Stopped")
        self.target_entry.configure(state=tk.NORMAL)
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.append_log("Results finalized.", "INFO")
        if self.close_after_stop:
            self.root.destroy()

    def append_log(self, message, tag):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, message + "\n", tag)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def draw_graph(self):
        canvas = self.graph
        canvas.delete("all")
        width = max(canvas.winfo_width(), 10)
        height = max(canvas.winfo_height(), 10)
        pad_l, pad_r, pad_t, pad_b = 48, 16, 16, 30
        plot_w = max(width - pad_l - pad_r, 1)
        plot_h = max(height - pad_t - pad_b, 1)

        canvas.create_text(pad_l, 8, anchor=tk.W, fill="#d1d5db", text="Last 5 minutes")
        canvas.create_line(pad_l, pad_t, pad_l, pad_t + plot_h, fill="#4b5563")
        canvas.create_line(pad_l, pad_t + plot_h, pad_l + plot_w, pad_t + plot_h, fill="#4b5563")

        now = self.samples[-1][0] if self.samples else datetime.now()
        cutoff = now - timedelta(seconds=GRAPH_WINDOW_SECONDS)
        visible = [(ts, lat) for ts, lat in self.samples if ts >= cutoff]
        latencies = [lat for _ts, lat in visible if lat is not None]
        y_max = max(100, max(latencies, default=0))
        y_max = ((y_max + 49) // 50) * 50

        for value in range(0, y_max + 1, max(50, y_max // 4 or 50)):
            y = pad_t + plot_h - (value / y_max) * plot_h
            canvas.create_line(pad_l, y, pad_l + plot_w, y, fill="#1f2937")
            canvas.create_text(pad_l - 8, y, anchor=tk.E, fill="#9ca3af", text=str(value))

        points = []
        for ts, lat in visible:
            seconds = max(0, min(GRAPH_WINDOW_SECONDS, (ts - cutoff).total_seconds()))
            x = pad_l + (seconds / GRAPH_WINDOW_SECONDS) * plot_w
            if lat is None:
                y = pad_t + 8
                canvas.create_line(x - 4, y - 4, x + 4, y + 4, fill="#ef4444", width=2)
                canvas.create_line(x - 4, y + 4, x + 4, y - 4, fill="#ef4444", width=2)
                continue
            y = pad_t + plot_h - (lat / y_max) * plot_h
            color = "#9ca3af" if lat < 50 else "#f59e0b" if lat <= 100 else "#ef4444"
            canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill=color, outline=color)
            points.append((x, y))

        for first, second in zip(points, points[1:]):
            canvas.create_line(first[0], first[1], second[0], second[1], fill="#60a5fa", width=1)

        canvas.create_text(pad_l, height - 8, anchor=tk.W, fill="#9ca3af", text="-5 min")
        canvas.create_text(pad_l + plot_w, height - 8, anchor=tk.E, fill="#9ca3af", text="now")


def main():
    root = tk.Tk()
    app = PingTuckzApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
