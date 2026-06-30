import queue
import threading
from collections import deque
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk

import ping_tuckz_core as core


GRAPH_DEFAULT_WINDOW_SECONDS = 60
GRAPH_MIN_WINDOW_SECONDS = 60
GRAPH_MAX_WINDOW_SECONDS = 1800
BG = "#1a1a1a"
PANEL = "#2a2a2a"
PANEL_ALT = "#1e2a3a"
BORDER = "#444444"
TEXT = "#e0e0e0"
MUTED = "#c0c8d0"
BLUE = "#4a9eff"
MEDIUM = "#ff8c00"
HIGH = "#ff4444"
TIMEOUT = "#ff6666"


class PingTuckzApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Ping Tuckz")
        self.root.geometry("980x680")
        self.root.minsize(760, 520)
        self.root.configure(bg=BG)
        self.root.overrideredirect(True)

        self.events = queue.Queue()
        self.samples = deque()
        self.worker = None
        self.stop_event = None
        self.close_after_stop = False
        self.maximized = False
        self.normal_geometry = None
        self.title_drag_offset_x = 0
        self.title_drag_offset_y = 0
        self.graph_window_seconds = GRAPH_DEFAULT_WINDOW_SECONDS
        self.graph_pan_seconds = 0
        self.drag_start_x = None
        self.drag_start_pan_seconds = 0

        self.target_var = tk.StringVar(value=core.DEFAULT_TARGET)
        self.status_var = tk.StringVar(value="Stopped")
        self.latest_var = tk.StringVar(value="Latest: -")
        self.files_var = tk.StringVar(value="Results: -")

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self.process_events)

    def _build_ui(self):
        self._configure_theme()

        shell = tk.Frame(self.root, bg=BORDER, bd=0, highlightthickness=0)
        shell.pack(fill=tk.BOTH, expand=True)

        self._build_title_bar(shell)

        outer = ttk.Frame(shell, padding=10, style="App.TFrame")
        outer.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(outer, style="App.TFrame")
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="Target", style="App.TLabel").pack(side=tk.LEFT)
        self.target_entry = ttk.Entry(controls, textvariable=self.target_var, width=32)
        self.target_entry.pack(side=tk.LEFT, padx=(6, 12))

        self.start_button = ttk.Button(controls, text="Start", command=self.start, style="App.TButton")
        self.start_button.pack(side=tk.LEFT)
        self.stop_button = ttk.Button(controls, text="Stop", command=self.stop, state=tk.DISABLED, style="App.TButton")
        self.stop_button.pack(side=tk.LEFT, padx=(6, 12))

        ttk.Label(controls, textvariable=self.status_var, style="App.TLabel").pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(controls, textvariable=self.latest_var, style="App.TLabel").pack(side=tk.LEFT)

        self.graph = tk.Canvas(outer, height=110, bg=BG, highlightthickness=1, highlightbackground=BORDER)
        self.graph.pack(fill=tk.X, pady=(10, 8))
        self.graph.bind("<Configure>", lambda _event: self.draw_graph())
        self.graph.bind("<ButtonPress-1>", self.on_graph_drag_start)
        self.graph.bind("<B1-Motion>", self.on_graph_drag)
        self.graph.bind("<ButtonRelease-1>", self.on_graph_drag_end)
        self.graph.bind("<MouseWheel>", self.on_graph_wheel)
        self.graph.bind("<Button-4>", self.on_graph_wheel)
        self.graph.bind("<Button-5>", self.on_graph_wheel)

        ttk.Label(outer, textvariable=self.files_var, style="Muted.TLabel").pack(fill=tk.X, anchor=tk.W)

        log_frame = tk.Frame(outer, bg=BORDER, highlightthickness=0, bd=0)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.log = tk.Text(
            log_frame,
            height=18,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 10),
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief=tk.FLAT,
            borderwidth=0,
            padx=8,
            pady=6,
            selectbackground=PANEL_ALT,
            selectforeground=TEXT,
        )
        self.log_scrollbar = ttk.Scrollbar(
            log_frame,
            orient=tk.VERTICAL,
            command=self.log.yview,
            style="Log.Vertical.TScrollbar",
        )
        self.log.configure(yscrollcommand=self.log_scrollbar.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(1, 0), pady=1)
        self.log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 1), pady=1)
        self.log.tag_configure("NORMAL", foreground="#b0b0b0")
        self.log.tag_configure("MEDIUM", foreground=MEDIUM)
        self.log.tag_configure("HIGH", foreground=HIGH)
        self.log.tag_configure("TIMEOUT", foreground=TIMEOUT)
        self.log.tag_configure("INFO", foreground=MUTED)
        self.log.tag_configure("ERROR", foreground=TIMEOUT)

    def _build_title_bar(self, parent):
        title_bar = tk.Frame(parent, bg=PANEL_ALT, height=34, bd=0, highlightthickness=0)
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)

        title_label = tk.Label(
            title_bar,
            text="Ping Tuckz",
            bg=PANEL_ALT,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
            anchor=tk.W,
            padx=10,
        )
        title_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for widget in (title_bar, title_label):
            widget.bind("<ButtonPress-1>", self.on_title_drag_start)
            widget.bind("<B1-Motion>", self.on_title_drag)
            widget.bind("<Double-Button-1>", lambda _event: self.toggle_maximize())

        self.minimize_button = self._title_button(title_bar, "_", self.minimize_window)
        self.maximize_button = self._title_button(title_bar, "[ ]", self.toggle_maximize)
        self.close_button = self._title_button(title_bar, "X", self.on_close, close=True)

    def _title_button(self, parent, text, command, close=False):
        button = tk.Label(
            parent,
            text=text,
            bg=PANEL_ALT,
            fg=TEXT,
            font=("Segoe UI", 10),
            width=5,
            anchor=tk.CENTER,
        )
        button.pack(side=tk.LEFT, fill=tk.Y)
        button.bind("<Button-1>", lambda _event: command())
        button.bind("<Enter>", lambda _event: button.configure(bg=TIMEOUT if close else BLUE, fg="#ffffff"))
        button.bind("<Leave>", lambda _event: button.configure(bg=PANEL_ALT, fg=TEXT))
        return button

    def _configure_theme(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background=BG)
        style.configure("App.TLabel", background=BG, foreground=TEXT)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure(
            "App.TButton",
            background=PANEL,
            foreground=TEXT,
            bordercolor=BORDER,
            focuscolor=BG,
            padding=(10, 5),
        )
        style.map(
            "App.TButton",
            background=[("active", PANEL_ALT), ("disabled", "#242424")],
            foreground=[("disabled", "#777777")],
            bordercolor=[("active", BLUE)],
        )
        style.configure(
            "TEntry",
            fieldbackground=PANEL,
            foreground=TEXT,
            insertcolor=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
        )
        style.map(
            "TEntry",
            fieldbackground=[("disabled", "#242424")],
            foreground=[("disabled", "#777777")],
        )
        style.configure(
            "Log.Vertical.TScrollbar",
            background=PANEL_ALT,
            troughcolor=BG,
            bordercolor=BORDER,
            darkcolor=PANEL_ALT,
            lightcolor=PANEL_ALT,
            arrowcolor=MUTED,
            relief=tk.FLAT,
            width=14,
        )
        style.map(
            "Log.Vertical.TScrollbar",
            background=[("active", BLUE), ("pressed", BLUE)],
            arrowcolor=[("active", TEXT), ("pressed", TEXT)],
        )

    def start(self):
        if self.worker and self.worker.is_alive():
            return

        target = self.target_var.get().strip() or core.DEFAULT_TARGET
        self.target_var.set(target)
        self.stop_event = threading.Event()
        self.close_after_stop = False
        self.samples.clear()
        self.graph_window_seconds = GRAPH_DEFAULT_WINDOW_SECONDS
        self.graph_pan_seconds = 0
        self.drag_start_x = None
        self.drag_start_pan_seconds = 0
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

    def on_title_drag_start(self, event):
        if self.maximized:
            return
        self.title_drag_offset_x = event.x_root - self.root.winfo_x()
        self.title_drag_offset_y = event.y_root - self.root.winfo_y()

    def on_title_drag(self, event):
        if self.maximized:
            return
        x = event.x_root - self.title_drag_offset_x
        y = event.y_root - self.title_drag_offset_y
        self.root.geometry(f"+{x}+{y}")

    def minimize_window(self):
        self.root.overrideredirect(False)
        self.root.iconify()
        self.root.after(50, self.restore_borderless)

    def restore_borderless(self):
        if self.root.state() == "normal":
            self.root.overrideredirect(True)
        else:
            self.root.after(50, self.restore_borderless)

    def toggle_maximize(self):
        if self.maximized:
            if self.normal_geometry:
                self.root.geometry(self.normal_geometry)
            self.maximized = False
            self.maximize_button.configure(text="[ ]")
            return

        self.normal_geometry = self.root.geometry()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.root.geometry(f"{screen_w}x{screen_h}+0+0")
        self.maximized = True
        self.maximize_button.configure(text="[]")

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
        self.graph_pan_seconds = min(self.graph_pan_seconds, self.get_max_pan_seconds())

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
        _top, bottom = self.log.yview()
        should_follow = bottom >= 0.999
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, message + "\n", tag)
        if should_follow:
            self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def get_latest_graph_time(self):
        return self.samples[-1][0] if self.samples else datetime.now()

    def get_max_pan_seconds(self):
        if not self.samples:
            return 0
        span_seconds = (self.get_latest_graph_time() - self.samples[0][0]).total_seconds()
        return max(0, span_seconds - self.graph_window_seconds)

    def clamp_graph_pan(self, value):
        return max(0, min(value, self.get_max_pan_seconds()))

    def clamp_graph_window(self, value):
        return max(GRAPH_MIN_WINDOW_SECONDS, min(value, GRAPH_MAX_WINDOW_SECONDS))

    def on_graph_drag_start(self, event):
        self.drag_start_x = event.x
        self.drag_start_pan_seconds = self.graph_pan_seconds

    def on_graph_drag(self, event):
        if self.drag_start_x is None:
            return
        width = max(self.graph.winfo_width(), 10)
        pad_l, pad_r = 48, 16
        plot_w = max(width - pad_l - pad_r, 1)
        delta_x = event.x - self.drag_start_x
        delta_seconds = (delta_x / plot_w) * self.graph_window_seconds
        self.graph_pan_seconds = self.clamp_graph_pan(self.drag_start_pan_seconds + delta_seconds)
        self.draw_graph()

    def on_graph_drag_end(self, _event):
        self.drag_start_x = None

    def on_graph_wheel(self, event):
        if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
            zoom_factor = 0.8
        else:
            zoom_factor = 1.25

        old_window = self.graph_window_seconds
        new_window = self.clamp_graph_window(old_window * zoom_factor)
        if new_window == old_window:
            return

        width = max(self.graph.winfo_width(), 10)
        pad_l, pad_r = 48, 16
        plot_w = max(width - pad_l - pad_r, 1)
        pointer_fraction = max(0, min(1, (event.x - pad_l) / plot_w))
        latest_time = self.get_latest_graph_time()
        old_right = latest_time - timedelta(seconds=self.graph_pan_seconds)
        pointer_time = old_right - timedelta(seconds=old_window * (1 - pointer_fraction))
        new_right = pointer_time + timedelta(seconds=new_window * (1 - pointer_fraction))

        self.graph_window_seconds = new_window
        self.graph_pan_seconds = self.clamp_graph_pan((latest_time - new_right).total_seconds())
        self.draw_graph()

    def format_axis_time(self, timestamp, crosses_midnight):
        time_text = timestamp.strftime("%I:%M:%S %p").lstrip("0").lower()
        if crosses_midnight:
            return f"{timestamp.strftime('%m-%d')} {time_text}"
        return time_text

    def draw_graph(self):
        canvas = self.graph
        canvas.delete("all")
        width = max(canvas.winfo_width(), 10)
        height = max(canvas.winfo_height(), 10)
        pad_l, pad_r, pad_t, pad_b = 48, 16, 16, 24
        plot_w = max(width - pad_l - pad_r, 1)
        plot_h = max(height - pad_t - pad_b, 1)

        window_minutes = self.graph_window_seconds / 60
        if window_minutes.is_integer():
            title = f"Last {int(window_minutes)} minute{'s' if window_minutes != 1 else ''}"
        else:
            title = f"Last {self.graph_window_seconds:.0f} seconds"
        canvas.create_text(pad_l, 8, anchor=tk.W, fill=BLUE, text=title)
        canvas.create_line(pad_l, pad_t, pad_l, pad_t + plot_h, fill=BORDER)
        canvas.create_line(pad_l, pad_t + plot_h, pad_l + plot_w, pad_t + plot_h, fill=BORDER)

        self.graph_pan_seconds = self.clamp_graph_pan(self.graph_pan_seconds)
        right_time = self.get_latest_graph_time() - timedelta(seconds=self.graph_pan_seconds)
        left_time = right_time - timedelta(seconds=self.graph_window_seconds)
        visible = [(ts, lat) for ts, lat in self.samples if left_time <= ts <= right_time]
        latencies = [lat for _ts, lat in visible if lat is not None]
        y_max = max(100, max(latencies, default=0))
        y_max = ((y_max + 49) // 50) * 50

        for value in range(0, y_max + 1, max(50, y_max // 4 or 50)):
            y = pad_t + plot_h - (value / y_max) * plot_h
            canvas.create_line(pad_l, y, pad_l + plot_w, y, fill="#242424")
            canvas.create_text(pad_l - 8, y, anchor=tk.E, fill=MUTED, text=str(value))

        points = []
        for ts, lat in visible:
            seconds = max(0, min(self.graph_window_seconds, (ts - left_time).total_seconds()))
            x = pad_l + (seconds / self.graph_window_seconds) * plot_w
            if lat is None:
                y = pad_t + 8
                canvas.create_line(x - 4, y - 4, x + 4, y + 4, fill=TIMEOUT, width=2)
                canvas.create_line(x - 4, y + 4, x + 4, y - 4, fill=TIMEOUT, width=2)
                continue
            y = pad_t + plot_h - (lat / y_max) * plot_h
            points.append((x, y))

        for first, second in zip(points, points[1:]):
            canvas.create_line(first[0], first[1], second[0], second[1], fill=BLUE, width=1)

        crosses_midnight = left_time.date() != right_time.date()
        for idx in range(5):
            fraction = idx / 4
            label_time = left_time + timedelta(seconds=self.graph_window_seconds * fraction)
            x = pad_l + plot_w * fraction
            anchor = tk.W if idx == 0 else tk.E if idx == 4 else tk.CENTER
            canvas.create_text(x, height - 8, anchor=anchor, fill=MUTED, text=self.format_axis_time(label_time, crosses_midnight))


def main():
    root = tk.Tk()
    app = PingTuckzApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
