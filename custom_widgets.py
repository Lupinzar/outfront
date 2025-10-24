from pathlib import Path
import tkinter as tk
from tkinter import ttk
from tkinter.font import Font

class UnitFrame(ttk.Frame):
    def __init__(self, container, id: int, name: str, **kwargs):
        super().__init__(container, **kwargs)
        self.id = id
        self.name = name
        self.name_label = tk.Label(self, text=self.name, anchor='w')
        self.status_text = tk.StringVar(value='Queued')
        self.status_label = tk.Label(self, textvariable=self.status_text)
        self.progress = ttk.Progressbar(self, maximum=1)
        self.name_label.grid(row=0, column=0, sticky='we')
        self.status_label.grid(row=0, column=1)
        self.progress.grid(row=0, column=2)
        self.columnconfigure(0, weight=1)

    def set_detail(self, message: str):
        '''For error messages or details
        '''
        detail_label = tk.Label(self, anchor='w', justify='left', text=message)
        detail_label.grid(row=1, column=0, columnspan=3, sticky='we')

    def update_progress(self, done: int, of: int):
        self.progress['value'] = float(done) / float(of)

    def set_status(self, status: str):
        self.status_text.set(status)


#used https://blog.teclado.com/tkinter-scrollable-frames/ as a base
class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.canvas = tk.Canvas(self)
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            '<Configure>',
            lambda ev: self.canvas.configure(
                scrollregion=self.canvas.bbox('all')
            )
        )

        self.window = self.canvas.create_window((0,0), window=self.scrollable_frame, anchor='nw')
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind(
            '<Configure>',
            lambda ev: self.resize_inner_frame(ev.width)#self.canvas.itemconfig(self.window, width=self.canvas.winfo_width() - 7)
        )
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def resize_inner_frame(self, width: int):
        bw = int(self.canvas.cget('borderwidth'))
        hlt = int(self.canvas.cget('highlightthickness'))
        rwidth = width - bw * 2 - hlt * 2
        self.canvas.itemconfig(self.window, width=rwidth)

    def clear(self):
        for child in self.scrollable_frame.winfo_children():
            child.destroy()
        self.scrollable_frame.config(height=1)
        