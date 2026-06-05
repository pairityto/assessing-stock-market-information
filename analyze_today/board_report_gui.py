import tkinter as tk
from tkinter import messagebox, ttk

from board_report_core import (
    CONFIG_PATH,
    SUPPORTED_PROVIDERS,
    SUPPORTED_SCOPES,
    analyze_selected_boards,
    load_config,
    refresh_catalog,
    sanitize_proxy_env,
    save_config,
    save_report_outputs,
    set_scope_selection,
)


class BoardReportApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("概念/板块日报配置")
        self.root.geometry("1120x760")
        self.config = load_config(CONFIG_PATH)
        self.trees = {}
        self.status_var = tk.StringVar(value=f"配置文件: {CONFIG_PATH}")
        self.provider_var = tk.StringVar(value=self.config["meta"].get("provider", "eastmoney"))
        self.lookback_var = tk.StringVar(value=str(self.config["meta"].get("lookback", 20)))
        self.topn_var = tk.StringVar(value=str(self.config["meta"].get("topn", 12)))
        self.sleep_var = tk.StringVar(value=str(self.config["meta"].get("sleep", 0.15)))
        self._build()
        self._load_trees_from_config()

    def _build(self) -> None:
        container = ttk.Frame(self.root, padding=14)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="概念/板块日报工具", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            container,
            text="双击表格中的“纳入分析”可切换开关；数据源支持 akshare、eastmoney、ths。",
        ).pack(anchor="w", pady=(4, 10))

        top = ttk.LabelFrame(container, text="全局设置", padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="数据源").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=6)
        provider_box = ttk.Combobox(top, textvariable=self.provider_var, values=list(SUPPORTED_PROVIDERS), state="readonly", width=16)
        provider_box.grid(row=0, column=1, sticky="w", pady=6)
        ttk.Label(top, text="统计窗口").grid(row=0, column=2, sticky="w", padx=(16, 8), pady=6)
        ttk.Entry(top, textvariable=self.lookback_var, width=10).grid(row=0, column=3, sticky="w", pady=6)
        ttk.Label(top, text="榜单条数").grid(row=0, column=4, sticky="w", padx=(16, 8), pady=6)
        ttk.Entry(top, textvariable=self.topn_var, width=10).grid(row=0, column=5, sticky="w", pady=6)
        ttk.Label(top, text="请求间隔").grid(row=0, column=6, sticky="w", padx=(16, 8), pady=6)
        ttk.Entry(top, textvariable=self.sleep_var, width=10).grid(row=0, column=7, sticky="w", pady=6)

        buttons = ttk.Frame(top)
        buttons.grid(row=1, column=0, columnspan=8, sticky="w", pady=(8, 0))
        ttk.Button(buttons, text="刷新板块清单", command=self.refresh).pack(side="left")
        ttk.Button(buttons, text="保存配置", command=self.save).pack(side="left", padx=8)
        ttk.Button(buttons, text="生成日报", command=self.run_report).pack(side="left")

        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True, pady=(12, 0))

        for scope in SUPPORTED_SCOPES:
            frame = ttk.Frame(notebook, padding=8)
            notebook.add(frame, text="行业板块" if scope == "industry" else "概念板块")
            self._build_scope_tab(frame, scope)

        ttk.Label(container, textvariable=self.status_var).pack(anchor="w", pady=(10, 0))

    def _build_scope_tab(self, parent: ttk.Frame, scope: str) -> None:
        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(0, 8))
        ttk.Button(actions, text="全选", command=lambda s=scope: self._set_all(s, True)).pack(side="left")
        ttk.Button(actions, text="全不选", command=lambda s=scope: self._set_all(s, False)).pack(side="left", padx=8)

        columns = ("selected", "board_name", "board_code")
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=24)
        tree.heading("selected", text="纳入分析")
        tree.heading("board_name", text="板块名称")
        tree.heading("board_code", text="板块代码")
        tree.column("selected", width=90, anchor="center")
        tree.column("board_name", width=460, anchor="w")
        tree.column("board_code", width=120, anchor="center")
        tree.pack(fill="both", expand=True)
        tree.bind("<Double-1>", lambda event, s=scope: self._toggle_selected(event, s))
        self.trees[scope] = tree

    def _load_trees_from_config(self) -> None:
        for scope, tree in self.trees.items():
            for item in tree.get_children():
                tree.delete(item)
            for item in self.config["scopes"][scope].get("board_catalog", []):
                selected = "是" if item.get("selected") else "否"
                tree.insert("", "end", values=(selected, item.get("board_name", ""), item.get("board_code", "")))

    def _collect_scope_selection(self, scope: str) -> list[str]:
        tree = self.trees[scope]
        selected = []
        for item_id in tree.get_children():
            selected_flag, board_name, _ = tree.item(item_id, "values")
            if selected_flag == "是":
                selected.append(board_name)
        return selected

    def _write_form_into_config(self) -> None:
        self.config["meta"]["provider"] = self.provider_var.get().strip()
        self.config["meta"]["lookback"] = int(self.lookback_var.get())
        self.config["meta"]["topn"] = int(self.topn_var.get())
        self.config["meta"]["sleep"] = float(self.sleep_var.get())
        for scope in SUPPORTED_SCOPES:
            self.config = set_scope_selection(self.config, scope, self._collect_scope_selection(scope))

    def _toggle_selected(self, event, scope: str) -> None:
        tree = self.trees[scope]
        item_id = tree.identify_row(event.y)
        if not item_id:
            return
        selected, board_name, board_code = tree.item(item_id, "values")
        tree.item(item_id, values=("否" if selected == "是" else "是", board_name, board_code))

    def _set_all(self, scope: str, enabled: bool) -> None:
        tree = self.trees[scope]
        value = "是" if enabled else "否"
        for item_id in tree.get_children():
            selected, board_name, board_code = tree.item(item_id, "values")
            tree.item(item_id, values=(value, board_name, board_code))

    def refresh(self) -> None:
        try:
            self._write_form_into_config()
            removed = sanitize_proxy_env()
            self.config = refresh_catalog(self.config, self.provider_var.get().strip())
            self._load_trees_from_config()
            self.status_var.set(
                "已刷新板块清单"
                + (f"，并清理代理: {'; '.join(removed)}" if removed else "")
            )
        except Exception as exc:
            messagebox.showerror("刷新失败", str(exc))

    def save(self) -> None:
        try:
            self._write_form_into_config()
            save_config(self.config, CONFIG_PATH)
            self.status_var.set(f"已保存配置: {CONFIG_PATH}")
            messagebox.showinfo("保存成功", f"配置已保存到\n{CONFIG_PATH}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def run_report(self) -> None:
        try:
            self._write_form_into_config()
            save_config(self.config, CONFIG_PATH)
            df = analyze_selected_boards(self.config)
            outputs = save_report_outputs(df, self.config)
            self.status_var.set(f"已生成日报: {outputs['csv'].name} / {outputs['html'].name}")
            messagebox.showinfo(
                "运行完成",
                f"已生成:\n{outputs['csv']}\n{outputs['html']}\n{outputs['config']}",
            )
        except Exception as exc:
            messagebox.showerror("运行失败", str(exc))


if __name__ == "__main__":
    root = tk.Tk()
    app = BoardReportApp(root)
    root.mainloop()
