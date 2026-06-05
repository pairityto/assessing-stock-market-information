import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from dual_sector_daily import DEFAULT_CONFIG_PATH, load_config, run_dual_sector_report, save_config


class DualSectorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("双板块日报配置")
        self.root.geometry("920x620")
        self.config_path = DEFAULT_CONFIG_PATH
        self.config = load_config(self.config_path)
        self.vars = {}
        self._build()

    def _build(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill="both", expand=True)

        title = ttk.Label(container, text="双板块日报配置", font=("Microsoft YaHei UI", 16, "bold"))
        title.pack(anchor="w")

        hint = ttk.Label(
            container,
            text="这里可以改两个板块的成分股 CSV、数据目录和策略参数。保存后可直接运行日报。",
        )
        hint.pack(anchor="w", pady=(4, 12))

        global_box = ttk.LabelFrame(container, text="全局参数", padding=12)
        global_box.pack(fill="x", pady=(0, 12))
        self._add_entry(global_box, "结束日期", "global.end_date", row=0, value=self.config["global"].get("end_date", ""))
        self._add_entry(global_box, "下载回看天数", "global.lookback_days_for_download", row=1, value=self.config["global"].get("lookback_days_for_download", 500))
        self._add_entry(global_box, "抽样池大小", "global.sample_size", row=2, value=self.config["global"].get("sample_size", 10000))
        self._add_entry(global_box, "推荐股票数", "global.top_n", row=3, value=self.config["global"].get("top_n", 10))
        strategy = self.config["global"].get("strategy", {})
        self._add_entry(global_box, "策略回看天数", "global.strategy.lookback_days", row=0, column_offset=3, value=strategy.get("lookback_days", 252))
        self._add_entry(global_box, "PE分位阈值", "global.strategy.percentile", row=1, column_offset=3, value=strategy.get("percentile", 0.2))
        self._add_entry(global_box, "最大持有天数", "global.strategy.max_hold_days", row=2, column_offset=3, value=strategy.get("max_hold_days", 90))
        self._add_entry(global_box, "止盈阈值", "global.strategy.stop_profit", row=3, column_offset=3, value=strategy.get("stop_profit", 0.25))

        for idx, sector in enumerate(self.config["sectors"]):
            sector_box = ttk.LabelFrame(container, text=f"板块 {idx + 1}", padding=12)
            sector_box.pack(fill="x", pady=(0, 12))
            prefix = f"sectors.{idx}"
            self._add_entry(sector_box, "板块名称", f"{prefix}.name", row=0, value=sector.get("name", ""))
            self._add_entry(sector_box, "代码列名", f"{prefix}.symbol_column", row=1, value=sector.get("symbol_column", "TickFlow代码"))
            self._add_entry(sector_box, "数据目录", f"{prefix}.data_root", row=2, value=sector.get("data_root", ""))
            self._add_checkbox(sector_box, "启用该板块", f"{prefix}.enabled", row=0, column=3, value=sector.get("enabled", True))

            csv_key = f"{prefix}.components_csv"
            self._add_entry(sector_box, "成分股CSV", csv_key, row=3, value=sector.get("components_csv", ""))
            browse_button = ttk.Button(
                sector_box,
                text="选择文件",
                command=lambda key=csv_key: self._choose_file(key),
            )
            browse_button.grid(row=3, column=3, sticky="w", padx=(8, 0), pady=6)

        buttons = ttk.Frame(container)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="保存配置", command=self.save).pack(side="left")
        ttk.Button(buttons, text="运行日报", command=self.run_report).pack(side="left", padx=8)
        ttk.Button(buttons, text="打开配置文件", command=self.show_config_path).pack(side="left")

        self.status_var = tk.StringVar(value=f"配置文件: {self.config_path}")
        ttk.Label(container, textvariable=self.status_var).pack(anchor="w", pady=(12, 0))

    def _add_entry(self, parent, label, key, row, value, column_offset=0):
        ttk.Label(parent, text=label).grid(row=row, column=column_offset, sticky="w", padx=(0, 8), pady=6)
        var = tk.StringVar(value=str(value))
        entry = ttk.Entry(parent, textvariable=var, width=34)
        entry.grid(row=row, column=column_offset + 1, sticky="ew", pady=6)
        self.vars[key] = var
        parent.grid_columnconfigure(column_offset + 1, weight=1)

    def _add_checkbox(self, parent, label, key, row, column, value):
        var = tk.BooleanVar(value=bool(value))
        check = ttk.Checkbutton(parent, text=label, variable=var)
        check.grid(row=row, column=column, sticky="w", pady=6)
        self.vars[key] = var

    def _choose_file(self, key: str) -> None:
        current = self.vars[key].get()
        initial_dir = str(Path(current).parent) if current else str(Path.cwd())
        selected = filedialog.askopenfilename(
            title="选择成分股CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=initial_dir,
        )
        if selected:
            self.vars[key].set(selected)

    def _collect_config(self):
        config = load_config(self.config_path)
        config["global"]["end_date"] = self.vars["global.end_date"].get().strip()
        config["global"]["lookback_days_for_download"] = int(self.vars["global.lookback_days_for_download"].get())
        config["global"]["sample_size"] = int(self.vars["global.sample_size"].get())
        config["global"]["top_n"] = int(self.vars["global.top_n"].get())
        config["global"]["strategy"]["lookback_days"] = int(self.vars["global.strategy.lookback_days"].get())
        config["global"]["strategy"]["percentile"] = float(self.vars["global.strategy.percentile"].get())
        config["global"]["strategy"]["max_hold_days"] = int(self.vars["global.strategy.max_hold_days"].get())
        config["global"]["strategy"]["stop_profit"] = float(self.vars["global.strategy.stop_profit"].get())

        for idx, sector in enumerate(config["sectors"]):
            prefix = f"sectors.{idx}"
            sector["name"] = self.vars[f"{prefix}.name"].get().strip()
            sector["symbol_column"] = self.vars[f"{prefix}.symbol_column"].get().strip()
            sector["data_root"] = self.vars[f"{prefix}.data_root"].get().strip()
            sector["components_csv"] = self.vars[f"{prefix}.components_csv"].get().strip()
            sector["enabled"] = bool(self.vars[f"{prefix}.enabled"].get())
        return config

    def save(self) -> None:
        try:
            config = self._collect_config()
            save_config(config, self.config_path)
            self.status_var.set(f"已保存配置: {self.config_path}")
            messagebox.showinfo("保存成功", f"配置已保存到\n{self.config_path}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def run_report(self) -> None:
        try:
            config = self._collect_config()
            save_config(config, self.config_path)
            result = run_dual_sector_report(self.config_path)
            self.status_var.set(f"运行完成，共生成 {len(result)} 条推荐")
            messagebox.showinfo("运行完成", f"日报已生成，共 {len(result)} 条记录。")
        except Exception as exc:
            messagebox.showerror("运行失败", str(exc))

    def show_config_path(self) -> None:
        self.status_var.set(f"配置文件路径: {self.config_path.resolve()}")


if __name__ == "__main__":
    root = tk.Tk()
    app = DualSectorApp(root)
    root.mainloop()
