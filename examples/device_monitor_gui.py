#!/usr/bin/env python
import argparse
import re
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
from typing import Dict, Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toyopuc import ToyopucHighLevelClient, resolve_device


class MonitorApp:
    BG = "#f4efe6"
    PANEL = "#fbf8f2"
    PANEL_ALT = "#f0e7d7"
    INK = "#1f1b17"
    MUTED = "#6b6257"
    ACCENT = "#0f766e"
    ACCENT_SOFT = "#d9f2ef"
    WARN = "#fff3bf"
    ERROR = "#f8d7da"
    OK = "#e7f6ec"
    DEVICE_HELP_TEXT = "Single, comma list, or range like P1-D0000-D000F"
    DEVICE_PART_RE = re.compile(r"^(?:(P[123])-)?([A-Z]{1,2})([0-9A-F]+)([WHL]?)$")
    DEVICE_RANGE_TOKEN_RE = re.compile(
        r"^(?P<left>(?:P[123]-)?[A-Z]{1,2}[0-9A-F]+[WHL]?)-(?P<right>(?:P[123]-)?[A-Z]{1,2}[0-9A-F]+[WHL]?)$"
    )

    def __init__(self, root: tk.Tk, args):
        self.root = root
        self.args = args
        self.root.title("toyopuc Device Monitor")
        self.root.geometry("1320x860")
        self.root.minsize(1100, 720)

        self.client: Optional[ToyopucHighLevelClient] = None
        self.poll_job: Optional[str] = None
        self.last_values: Dict[str, object] = {}
        self.units: Dict[str, str] = {}
        self.interval_ms = int(args.interval * 1000)

        self.device_var = tk.StringVar(value="P1-D0000")
        self.device_hint_var = tk.StringVar(value=self.DEVICE_HELP_TEXT)
        self.value_var = tk.StringVar(value="0x1234")
        self.interval_var = tk.StringVar(value=f"{self.args.interval:.1f}")
        self.host_var = tk.StringVar(value=self.args.host)
        self.port_var = tk.StringVar(value=str(self.args.port))
        self.protocol_var = tk.StringVar(value=self.args.protocol)
        self.local_port_var = tk.StringVar(value=str(self.args.local_port))
        self.timeout_var = tk.StringVar(value=f"{self.args.timeout:g}")
        self.retries_var = tk.StringVar(value=str(self.args.retries))
        self.hops_var = tk.StringVar(value=self.args.hops)
        self.endpoint_var = tk.StringVar(value=self._endpoint_text())
        self.connection_var = tk.StringVar(value="disconnected")
        self.watch_count_var = tk.StringVar(value="0 devices")
        self.last_poll_var = tk.StringVar(value="not polled yet")
        self.selected_var = tk.StringVar(value="-")
        self.status_var = tk.StringVar(value="Ready")

        for var in (self.host_var, self.port_var, self.protocol_var, self.local_port_var, self.hops_var):
            var.trace_add("write", self._on_connection_field_change)
        self.device_var.trace_add("write", self._on_device_input_change)

        self._configure_style()
        self._build_ui()
        self._on_device_input_change()
        self._connect(report_dialog=False)
        if args.watch:
            self._add_devices(" ".join(args.watch), log=False)
        self._log(
            f"initial watch list = {', '.join(args.watch) if args.watch else 'none'}",
            level="INFO",
        )
        self._refresh_watch_count()
        self._schedule_poll()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _endpoint_text(self) -> str:
        host = self.host_var.get().strip() or "<enter host>"
        port = self.port_var.get().strip() or "?"
        protocol = self.protocol_var.get().strip() or "tcp"
        local_port = self.local_port_var.get().strip()
        hops = self.hops_var.get().strip()
        if protocol == "udp" and local_port and local_port != "0":
            base = f"{host}:{port} over {protocol} (local {local_port})"
        else:
            base = f"{host}:{port} over {protocol}"
        if hops:
            return f"{base} via {hops}"
        return base

    def _configure_style(self):
        self.root.configure(background=self.BG)
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("App.TFrame", background=self.BG)
        style.configure("Card.TFrame", background=self.PANEL)
        style.configure("Card.TLabelframe", background=self.PANEL, borderwidth=1, relief="solid")
        style.configure("Card.TLabelframe.Label", background=self.PANEL, foreground=self.INK, font=("Segoe UI", 10, "bold"))
        style.configure("Title.TLabel", background=self.BG, foreground=self.INK, font=("Segoe UI Semibold", 19, "bold"))
        style.configure("Subtitle.TLabel", background=self.BG, foreground=self.MUTED, font=("Segoe UI", 10))
        style.configure("Meta.TLabel", background=self.PANEL, foreground=self.MUTED, font=("Segoe UI", 9))
        style.configure("Value.TLabel", background=self.PANEL, foreground=self.INK, font=("Consolas", 10, "bold"))
        style.configure("Status.TLabel", background=self.PANEL_ALT, foreground=self.INK, padding=(10, 6))
        style.configure("TButton", padding=(10, 6))
        style.configure("DeviceOk.TEntry", fieldbackground="#ffffff")
        style.configure("DeviceError.TEntry", fieldbackground=self.ERROR)
        style.configure("Accent.TButton", padding=(12, 7), background=self.ACCENT, foreground="#ffffff")
        style.map(
            "Accent.TButton",
            background=[("active", "#0c5f59"), ("pressed", "#0b514d")],
            foreground=[("disabled", "#d0d0d0"), ("!disabled", "#ffffff")],
        )
        style.configure(
            "Treeview",
            rowheight=28,
            font=("Segoe UI", 10),
            fieldbackground="#ffffff",
            background="#ffffff",
            foreground=self.INK,
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI Semibold", 10, "bold"),
            background=self.PANEL_ALT,
            foreground=self.INK,
            relief="flat",
        )
        style.map("Treeview.Heading", background=[("active", "#e6dccd")])

    def _build_ui(self):
        container = ttk.Frame(self.root, padding=16, style="App.TFrame")
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container, style="App.TFrame")
        header.pack(fill="x")
        title_block = ttk.Frame(header, style="App.TFrame")
        title_block.pack(side="left", fill="x", expand=True)
        ttk.Label(title_block, text="Device Monitor", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title_block,
            text="Live watch table, single-point read/write, and quick CPU clock/status checks.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        connection_card = ttk.Frame(header, style="Card.TFrame", padding=(14, 10))
        connection_card.pack(side="right")
        ttk.Label(connection_card, text="Endpoint", style="Meta.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(connection_card, textvariable=self.endpoint_var, style="Value.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Label(connection_card, text="Connection", style="Meta.TLabel").grid(row=0, column=1, sticky="w", padx=(18, 0))
        ttk.Label(connection_card, textvariable=self.connection_var, style="Value.TLabel").grid(row=1, column=1, sticky="w", padx=(18, 0))

        content = ttk.Frame(container, style="App.TFrame")
        content.pack(fill="both", expand=True, pady=(16, 0))
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(content, style="App.TFrame")
        sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 16))

        monitor_area = ttk.Frame(content, style="App.TFrame")
        monitor_area.grid(row=0, column=1, sticky="nsew")
        monitor_area.columnconfigure(0, weight=1)
        monitor_area.rowconfigure(0, weight=1)

        connection_controls = ttk.LabelFrame(sidebar, text="Connection", style="Card.TLabelframe", padding=12)
        connection_controls.pack(fill="x")
        connection_controls.columnconfigure(1, weight=1)

        ttk.Label(connection_controls, text="Host", style="Meta.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(connection_controls, textvariable=self.host_var, width=20).grid(row=0, column=1, columnspan=2, sticky="ew")

        ttk.Label(connection_controls, text="Port", style="Meta.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(connection_controls, textvariable=self.port_var, width=10).grid(row=1, column=1, sticky="ew", pady=(10, 0))
        ttk.Label(connection_controls, text="Protocol", style="Meta.TLabel").grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(10, 0))
        protocol_box = ttk.Combobox(
            connection_controls,
            textvariable=self.protocol_var,
            values=("tcp", "udp"),
            width=8,
            state="readonly",
        )
        protocol_box.grid(row=1, column=3, sticky="ew", pady=(10, 0))

        ttk.Label(connection_controls, text="Local UDP Port", style="Meta.TLabel").grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(connection_controls, textvariable=self.local_port_var, width=10).grid(row=2, column=1, sticky="ew", pady=(10, 0))
        ttk.Label(connection_controls, text="Timeout", style="Meta.TLabel").grid(row=2, column=2, sticky="w", padx=(8, 0), pady=(10, 0))
        ttk.Entry(connection_controls, textvariable=self.timeout_var, width=8).grid(row=2, column=3, sticky="ew", pady=(10, 0))

        ttk.Label(connection_controls, text="Retries", style="Meta.TLabel").grid(row=3, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(connection_controls, textvariable=self.retries_var, width=10).grid(row=3, column=1, sticky="ew", pady=(10, 0))
        ttk.Label(connection_controls, text="Relay hops", style="Meta.TLabel").grid(row=3, column=2, sticky="w", padx=(8, 0), pady=(10, 0))
        ttk.Entry(connection_controls, textvariable=self.hops_var, width=18).grid(row=3, column=3, sticky="ew", pady=(10, 0))

        connect_row = ttk.Frame(connection_controls, style="Card.TFrame")
        connect_row.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        for column in range(3):
            connect_row.columnconfigure(column, weight=1)
        ttk.Button(connect_row, text="Connect", command=self._on_reconnect, style="Accent.TButton").grid(row=0, column=0, sticky="ew")
        ttk.Button(connect_row, text="Disconnect", command=self._on_disconnect).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(connect_row, text="Refresh Label", command=self._refresh_endpoint_preview).grid(row=0, column=2, sticky="ew")

        watch_card = ttk.LabelFrame(sidebar, text="Watch Controls", style="Card.TLabelframe", padding=12)
        watch_card.pack(fill="x", pady=(14, 0))
        watch_card.columnconfigure(1, weight=1)

        ttk.Label(watch_card, text="Device", style="Meta.TLabel").grid(row=0, column=0, sticky="w")
        self.device_entry = ttk.Entry(
            watch_card,
            textvariable=self.device_var,
            width=20,
            style="DeviceOk.TEntry",
        )
        self.device_entry.grid(row=0, column=1, sticky="ew")
        ttk.Button(watch_card, text="Add", command=self._on_add, style="Accent.TButton").grid(row=0, column=2, padx=(6, 0))
        ttk.Label(
            watch_card,
            textvariable=self.device_hint_var,
            style="Meta.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        ttk.Label(watch_card, text="Value", style="Meta.TLabel").grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(watch_card, textvariable=self.value_var, width=20).grid(row=2, column=1, sticky="ew", pady=(10, 0))
        ttk.Button(watch_card, text="Write", command=self._on_write).grid(row=2, column=2, padx=(6, 0), pady=(10, 0))

        ttk.Label(watch_card, text="Interval (s)", style="Meta.TLabel").grid(row=3, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(watch_card, textvariable=self.interval_var, width=20).grid(row=3, column=1, sticky="ew", pady=(10, 0))
        ttk.Button(watch_card, text="Apply", command=self._on_interval).grid(row=3, column=2, padx=(6, 0), pady=(10, 0))

        action_row = ttk.Frame(watch_card, style="Card.TFrame")
        action_row.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        for column in range(3):
            action_row.columnconfigure(column, weight=1)
        ttk.Button(action_row, text="Read Selected", command=self._on_read).grid(row=0, column=0, sticky="ew")
        ttk.Button(action_row, text="Remove Selected", command=self._on_remove).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(action_row, text="Poll Now", command=self._on_poll_now, style="Accent.TButton").grid(row=0, column=2, sticky="ew")

        tools_card = ttk.LabelFrame(sidebar, text="PLC Actions", style="Card.TLabelframe", padding=12)
        tools_card.pack(fill="x", pady=(14, 0))
        for column in range(2):
            tools_card.columnconfigure(column, weight=1)
        ttk.Button(tools_card, text="Read Clock", command=self._on_clock).grid(row=0, column=0, sticky="ew")
        ttk.Button(tools_card, text="Read Status", command=self._on_status).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(tools_card, text="Clear Log", command=self._on_clear_log).grid(row=1, column=0, sticky="ew", pady=(8, 0))

        session_card = ttk.LabelFrame(sidebar, text="Session", style="Card.TLabelframe", padding=12)
        session_card.pack(fill="x", pady=(14, 0))
        self._session_row(session_card, 0, "Watched", self.watch_count_var)
        self._session_row(session_card, 1, "Selected", self.selected_var)
        self._session_row(session_card, 2, "Last poll", self.last_poll_var)

        monitor_card = ttk.LabelFrame(monitor_area, text="Monitor", style="Card.TLabelframe", padding=12)
        monitor_card.grid(row=0, column=0, sticky="nsew")
        monitor_card.columnconfigure(0, weight=1)
        monitor_card.rowconfigure(0, weight=1)

        tree_frame = ttk.Frame(monitor_card, style="Card.TFrame")
        tree_frame.grid(row=0, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("device", "scheme", "unit", "state", "value", "updated"),
            show="headings",
            height=15,
        )
        self.tree.heading("device", text="Device")
        self.tree.heading("scheme", text="Scheme")
        self.tree.heading("unit", text="Unit")
        self.tree.heading("state", text="State")
        self.tree.heading("value", text="Value")
        self.tree.heading("updated", text="Updated")
        self.tree.column("device", width=130, anchor="w")
        self.tree.column("scheme", width=120, anchor="w")
        self.tree.column("unit", width=70, anchor="center")
        self.tree.column("state", width=90, anchor="center")
        self.tree.column("value", width=140, anchor="w")
        self.tree.column("updated", width=130, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.tag_configure("ok", background="#ffffff")
        self.tree.tag_configure("changed", background=self.WARN)
        self.tree.tag_configure("error", background=self.ERROR)

        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        xscroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        log_card = ttk.LabelFrame(monitor_area, text="Event Log", style="Card.TLabelframe", padding=12)
        log_card.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        log_card.columnconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(
            log_card,
            height=10,
            wrap="word",
            font=("Consolas", 10),
            background="#fffdf8",
            foreground=self.INK,
            insertbackground=self.INK,
            relief="flat",
            borderwidth=0,
        )
        self.log_text.grid(row=0, column=0, sticky="ew")
        self.log_text.tag_configure("INFO", foreground=self.INK)
        self.log_text.tag_configure("WARN", foreground="#8a5a00")
        self.log_text.tag_configure("ERROR", foreground="#a61e2b")
        self.log_text.configure(state="disabled")

        footer = ttk.Label(container, textvariable=self.status_var, style="Status.TLabel")
        footer.pack(fill="x", pady=(14, 0))

    def _session_row(self, parent: ttk.LabelFrame, row: int, label: str, variable: tk.StringVar):
        ttk.Label(parent, text=label, style="Meta.TLabel").grid(row=row, column=0, sticky="w")
        ttk.Label(parent, textvariable=variable, style="Value.TLabel").grid(row=row, column=1, sticky="w", padx=(12, 0))

    def _log(self, line: str, level: str = "INFO"):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{stamp}] {level:<5} {line}\n", (level,))
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.status_var.set(line)

    def _set_connection_state(self, text: str):
        self.connection_var.set(text)

    def _refresh_endpoint_preview(self):
        self.endpoint_var.set(self._endpoint_text())

    def _on_connection_field_change(self, *_args):
        self._refresh_endpoint_preview()

    def _refresh_watch_count(self):
        count = len(self.tree.get_children(""))
        suffix = "device" if count == 1 else "devices"
        self.watch_count_var.set(f"{count} {suffix}")

    def _relay_hops(self) -> Optional[str]:
        hops = self.hops_var.get().strip()
        return hops or None

    def _relay_active(self) -> bool:
        return self._relay_hops() is not None

    def _require_client(self) -> ToyopucHighLevelClient:
        if self.client is None:
            raise RuntimeError("not connected")
        return self.client

    def _close_client(self):
        if self.client is None:
            return
        try:
            self.client.close()
        except Exception:
            pass
        self.client = None

    def _read_connection_settings(self):
        host = self.host_var.get().strip()
        if not host:
            raise ValueError("host is required")
        port = int(self.port_var.get().strip(), 0)
        protocol = self.protocol_var.get().strip() or "tcp"
        local_port = int(self.local_port_var.get().strip() or "0", 0)
        timeout = float(self.timeout_var.get().strip())
        retries = int(self.retries_var.get().strip() or "0", 0)
        hops = self._relay_hops()
        if port <= 0:
            raise ValueError("port must be greater than zero")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if retries < 0:
            raise ValueError("retries must be zero or greater")
        return {
            "host": host,
            "port": port,
            "protocol": protocol,
            "local_port": local_port,
            "timeout": timeout,
            "retries": retries,
            "hops": hops,
        }

    def _connect(self, report_dialog: bool):
        self._close_client()
        self._refresh_endpoint_preview()
        if not self.host_var.get().strip():
            self._set_connection_state("not configured")
            self._log("connection not attempted: enter host and press Connect", level="WARN")
            return
        try:
            settings = self._read_connection_settings()
            client = ToyopucHighLevelClient(
                settings["host"],
                settings["port"],
                protocol=settings["protocol"],
                local_port=settings["local_port"],
                timeout=settings["timeout"],
                retries=settings["retries"],
            )
            client.connect()
            self.client = client
            self._set_connection_state("connected")
            self._log(f"connected: {self._endpoint_text()}")
        except Exception as exc:
            self.client = None
            self._set_connection_state("connect failed")
            self._log(f"connect failed: {exc}", level="ERROR")
            if report_dialog:
                messagebox.showerror("Connect", str(exc))

    def _on_reconnect(self):
        self._connect(report_dialog=True)

    def _on_disconnect(self):
        self._close_client()
        self._set_connection_state("disconnected")
        self._log("disconnected")

    def _read_device_value(self, device: str):
        client = self._require_client()
        hops = self._relay_hops()
        resolved = resolve_device(device)
        if hops:
            return resolved, client.relay_read(hops, resolved)
        return resolved, client.read(device)

    def _write_device_value(self, device: str, value: int):
        client = self._require_client()
        hops = self._relay_hops()
        resolved = resolve_device(device)
        if hops:
            client.relay_write(hops, resolved, value)
            return resolved
        client.write(device, value)
        return resolved

    @staticmethod
    def _as_int(value: object) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        raise TypeError(f"unsupported value type: {type(value)!r}")

    def _format_value(self, unit: str, value: object) -> str:
        if unit == "bit":
            return "1" if bool(value) else "0"
        if unit == "byte":
            ivalue = self._as_int(value)
            return f"0x{ivalue & 0xFF:02X}"
        ivalue = self._as_int(value)
        return f"0x{ivalue & 0xFFFF:04X}"

    def _selected_device(self) -> Optional[str]:
        selection = self.tree.selection()
        if selection:
            return str(selection[0])
        device = self.device_var.get().strip().upper()
        return device if device else None

    def _select_device(self, device: str):
        if self.tree.exists(device):
            self.tree.selection_set(device)
            self.tree.focus(device)
            self.tree.see(device)
        self.device_var.set(device)
        self.selected_var.set(device)

    def _on_tree_select(self, _event=None):
        device = self._selected_device()
        if device:
            self.device_var.set(device)
            self.selected_var.set(device)

    def _add_device(self, device: str, log: bool = True):
        resolved = resolve_device(device)
        key = resolved.text
        self.units[key] = resolved.unit
        if not self.tree.exists(key):
            self.tree.insert(
                "",
                "end",
                iid=key,
                values=(key, resolved.scheme, resolved.unit, "watching", "-", "-"),
                tags=("ok",),
            )
        self._refresh_watch_count()
        self._select_device(key)
        if log:
            self._log(f"watch add: {key}")

    @classmethod
    def _expand_device_token(cls, token: str) -> list[str]:
        token = token.strip().upper()
        if not token:
            return []
        single_match = cls.DEVICE_PART_RE.fullmatch(token)
        if single_match:
            return [token]

        range_match = cls.DEVICE_RANGE_TOKEN_RE.fullmatch(token)
        if not range_match:
            raise ValueError(f"invalid device syntax: {token}")

        start_text = range_match.group("left")
        end_text = range_match.group("right")
        start_match = cls.DEVICE_PART_RE.fullmatch(start_text)
        end_match = cls.DEVICE_PART_RE.fullmatch(end_text)
        if not start_match or not end_match:
            raise ValueError(f"invalid range syntax: {token}")

        start_program, start_area, start_digits, start_suffix = start_match.groups()
        end_program, end_area, end_digits, end_suffix = end_match.groups()

        if start_program and end_program and start_program != end_program:
            raise ValueError(f"range must keep the same program prefix: {token}")
        program = start_program or end_program

        if start_area != end_area or start_suffix != end_suffix:
            raise ValueError(f"range must keep the same device family and suffix: {token}")
        if len(start_digits) != len(end_digits):
            raise ValueError(f"range must keep the same digit width: {token}")

        start_value = int(start_digits, 16)
        end_value = int(end_digits, 16)
        if end_value < start_value:
            raise ValueError(f"range end must be greater than or equal to start: {token}")

        width = len(start_digits)
        program_prefix = f"{program}-" if program else ""
        return [
            f"{program_prefix}{start_area}{value:0{width}X}{start_suffix}"
            for value in range(start_value, end_value + 1)
        ]

    @classmethod
    def _parse_device_input(cls, text: str) -> list[str]:
        raw_tokens = [part for part in re.split(r"[\s,;]+", text.strip()) if part]
        if not raw_tokens:
            raise ValueError("device is required")
        devices: list[str] = []
        for token in raw_tokens:
            devices.extend(cls._expand_device_token(token))
        return devices

    @classmethod
    def parse_and_validate_device_input(cls, text: str) -> list[str]:
        devices = cls._parse_device_input(text)
        for device in devices:
            resolve_device(device)
        return devices

    def _set_device_input_state(self, valid: bool, message: str):
        self.device_hint_var.set(message)
        if valid:
            self.device_entry.configure(style="DeviceOk.TEntry")
            return
        self.device_entry.configure(style="DeviceError.TEntry")

    def _validate_device_input_for_ui(self, text: str) -> tuple[bool, str]:
        if not text.strip():
            return True, self.DEVICE_HELP_TEXT
        try:
            devices = self.parse_and_validate_device_input(text)
        except Exception as exc:
            return False, f"Invalid: {exc}"
        if len(devices) == 1:
            return True, f"Valid: {devices[0]}"
        return True, f"Valid: {len(devices)} devices"

    def _on_device_input_change(self, *_args):
        valid, message = self._validate_device_input_for_ui(self.device_var.get())
        self._set_device_input_state(valid, message)

    def _add_devices(self, text: str, log: bool = True):
        devices = self.parse_and_validate_device_input(text)
        added: list[str] = []
        for device in devices:
            resolved = resolve_device(device)
            key = resolved.text
            self.units[key] = resolved.unit
            if not self.tree.exists(key):
                self.tree.insert(
                    "",
                    "end",
                    iid=key,
                    values=(key, resolved.scheme, resolved.unit, "watching", "-", "-"),
                    tags=("ok",),
                )
            added.append(key)

        self._refresh_watch_count()
        self._select_device(added[-1])
        if log:
            preview = ", ".join(added[:4])
            if len(added) > 4:
                preview += f", ... (+{len(added) - 4} more)"
            self._log(f"watch add: {preview}")

    def _on_add(self):
        try:
            self._add_devices(self.device_var.get())
        except Exception as exc:
            self._set_device_input_state(False, f"Invalid: {exc}")
            messagebox.showerror("Add device", str(exc))

    def _on_remove(self):
        device = self._selected_device()
        if not device:
            return
        if self.tree.exists(device):
            self.tree.delete(device)
        self.units.pop(device, None)
        self.last_values.pop(device, None)
        self.selected_var.set("-")
        self._refresh_watch_count()
        self._log(f"watch remove: {device}")

    def _on_read(self):
        device = self._selected_device()
        if not device:
            return
        try:
            resolved, value = self._read_device_value(device)
            formatted = self._format_value(resolved.unit, value)
            self._update_tree_row(device, resolved.scheme, resolved.unit, "manual", formatted, tags=("ok",))
            source = f" via {self._relay_hops()}" if self._relay_active() else ""
            self._log(f"{resolved.text} = {formatted}{source}")
        except Exception as exc:
            messagebox.showerror("Read", str(exc))

    def _parse_write_value(self, device: str, text: str) -> int:
        resolved = resolve_device(device)
        value = int(text, 0)
        if resolved.unit == "bit" and value not in (0, 1):
            raise ValueError("bit value must be 0 or 1")
        if resolved.unit == "byte" and not 0 <= value <= 0xFF:
            raise ValueError("byte value must be 0x00-0xFF")
        if resolved.unit == "word" and not 0 <= value <= 0xFFFF:
            raise ValueError("word value must be 0x0000-0xFFFF")
        return value

    def _on_write(self):
        device = self._selected_device()
        if not device:
            return
        try:
            value = self._parse_write_value(device, self.value_var.get().strip())
            resolved = self._write_device_value(device, value)
            self._log(
                f"{device} <= {self._format_value(resolved.unit, value)}"
                f"{f' via {self._relay_hops()}' if self._relay_active() else ''}"
            )
            self._poll_once()
        except Exception as exc:
            messagebox.showerror("Write", str(exc))

    def _safe_clock_text(self, clock) -> str:
        try:
            return clock.as_datetime().isoformat(sep=" ")
        except Exception:
            return "unavailable"

    def _on_clock(self):
        try:
            client = self._require_client()
            hops = self._relay_hops()
            clock = client.relay_read_clock(hops) if hops else client.read_clock()
            dt_text = self._safe_clock_text(clock)
            suffix = f" via {hops}" if hops else ""
            self._log(f"clock: {dt_text} (wd={clock.weekday}){suffix}")
        except Exception as exc:
            messagebox.showerror("Clock", str(exc))

    def _on_status(self):
        try:
            client = self._require_client()
            hops = self._relay_hops()
            status = client.relay_read_cpu_status(hops) if hops else client.read_cpu_status()
            run_state = "RUN" if status.run else "STOP"
            mode = "PC10" if status.pc10_mode else "PC3"
            flags = [mode]
            if status.alarm:
                flags.append("ALARM")
            running_programs = [
                name
                for enabled, name in (
                    (status.program1_running, "P1"),
                    (status.program2_running, "P2"),
                    (status.program3_running, "P3"),
                )
                if enabled
            ]
            if running_programs:
                flags.append(",".join(running_programs))
            suffix = f" via {hops}" if hops else ""
            self._log(f"status: {run_state} ({' / '.join(flags)}){suffix}")
        except Exception as exc:
            messagebox.showerror("Status", str(exc))

    def _on_interval(self):
        try:
            interval_sec = float(self.interval_var.get())
            if interval_sec <= 0:
                raise ValueError("interval must be greater than zero")
            self.interval_ms = int(interval_sec * 1000)
            self._log(f"interval set: {self.interval_ms} ms")
            self._schedule_poll(reset=True)
        except Exception as exc:
            messagebox.showerror("Interval", str(exc))

    def _on_poll_now(self):
        self._poll_once()

    def _on_clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.status_var.set("Log cleared")

    def _update_tree_row(
        self,
        device: str,
        scheme: str,
        unit: str,
        state: str,
        value: str,
        tags=(),
    ):
        self.tree.item(
            device,
            values=(device, scheme, unit, state, value, datetime.now().strftime("%H:%M:%S")),
            tags=tags,
        )

    def _poll_once(self):
        if self.poll_job is not None:
            self.root.after_cancel(self.poll_job)
            self.poll_job = None

        if self.client is None:
            self.last_poll_var.set("skipped (not connected)")
            self._schedule_poll()
            return

        for device in self.tree.get_children(""):
            unit = self.units[device]
            try:
                resolved, value = self._read_device_value(device)
                formatted = self._format_value(unit, value)
                changed = device in self.last_values and self.last_values[device] != value
                self.last_values[device] = value
                state = "changed" if changed else "ok"
                tags = ("changed",) if changed else ("ok",)
                self._update_tree_row(device, resolved.scheme, unit, state, formatted, tags=tags)
            except Exception as exc:
                resolved = resolve_device(device)
                self._update_tree_row(device, resolved.scheme, unit, "error", f"ERROR: {exc}", tags=("error",))

        self.last_poll_var.set(datetime.now().strftime("%H:%M:%S"))
        self._schedule_poll()

    def _schedule_poll(self, reset: bool = False):
        if reset and self.poll_job is not None:
            self.root.after_cancel(self.poll_job)
            self.poll_job = None
        if self.poll_job is None:
            self.poll_job = self.root.after(self.interval_ms, self._poll_once)

    def _on_close(self):
        if self.poll_job is not None:
            self.root.after_cancel(self.poll_job)
        self._close_client()
        self.root.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description="Tkinter device monitor example for toyopuc-computerlink")
    parser.add_argument("--host", default="")
    parser.add_argument("--port", type=int, default=1025)
    parser.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    parser.add_argument("--local-port", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--retries", type=int, default=0)
    parser.add_argument("--hops", default="")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--watch", nargs="*", default=["P1-M0000", "P1-D0000"])
    args = parser.parse_args()

    root = tk.Tk()
    MonitorApp(root, args)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
