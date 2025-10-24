from typing import Callable
from pathlib import Path
from time import time
import json
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox, filedialog
from enum import Enum
from pngunit import WorkOrder, PngUnit
import pngthreads as pt
from custom_widgets import ScrollableFrame, UnitFrame


_LAYOUT = {}
#emulates post increment
def _layout_increment(key: str) -> int:
    ret = _LAYOUT.get(key, 0)
    _LAYOUT[key] = ret + 1
    return ret

def _layout_reset(key: str):
    ret = _LAYOUT[key] = 0

def _layout_value(key: str) -> int:
    return _LAYOUT.get(key, 0)

class App(tk.Tk):
    class STATE(Enum):
        IDLE = 0
        RUNNING = 1
        STOPPING = 2

    FILTERS = [
        'None',
        'Sub',
        'Up',
        'Average',
        'Paeth',
        'Mixed',
        'Reuse'
    ]

    CONFIG_PATH = Path.cwd() / 'config.json'
    THREAD_CHECK_TIME = 200

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.manager: pt.Manager
        self.current_state = self.STATE.IDLE
        self.work_path: Path = Path.cwd()
        self.files_done: int = 0
        self.files_total: int = 0
        self.error_count: int = 0
        self.units: dict[int, UnitFrame] = {}
        self.start_time: float = 0
        self.end_time: float = 0
        self.size_savings: int = 0

        #these are not Tk events, but custom ones in the pngthreads module
        self.event_map = {
            pt.SessionStartEvent: self.handle_start,
            pt.SessionEndEvent: self.handle_end,
            pt.SessionQueueEvent: self.handle_queued,
            pt.PngUpdateEvent: self.handle_unit_update,
            pt.PngErrorEvent: self.handle_unit_error,
            pt.PngDoneEvent: self.handle_unit_done,
        }

        #tk binds
        self.thread_count = tk.IntVar(value=4)
        self.path_text = tk.StringVar(value=str(Path.cwd()))
        self.recursive = tk.BooleanVar()
        self.filter_bools: list[tk.BooleanVar] = []
        self.keep_pal = tk.BooleanVar()

        #region widget creation and layout
        #tk layout sucks...
        li = _layout_increment
        lr = _layout_reset
        lv = _layout_value

        default_padding = 2

        self._icon_img = tk.PhotoImage(file='./icon.png')
        self.iconphoto(False, self._icon_img)

        #directory, etc
        self._open_img = tk.PhotoImage(file='./folder-open.png')
        tk.Label(self, text='File or Directory Path:').grid(row=lv('mr'), column=li('mc'), padx=default_padding, pady=default_padding)
        self.path_entry = tk.Entry(self, textvariable=self.path_text)
        self.path_entry.grid(row=lv('mr'), column=li('mc'), padx=default_padding, pady=default_padding, sticky='we')
        #self.path_entry['width'] = 50
        self.path_select = tk.Button(self, text='Open', image=self._open_img, compound='left', command=self.open_path)
        self.path_select.grid(row=lv('mr'), column=li('mc'), padx=(0, default_padding), pady=default_padding)
        lr('mc')
        li('mr')

        #main options
        opt_frame = tk.Frame(self)
        self.recursive_check = tk.Checkbutton(opt_frame, text='Recursive', variable=self.recursive)
        self.recursive_check.grid(row=0, column=2, padx=default_padding, pady=default_padding)
        self.threads_box = tk.Spinbox(opt_frame, from_=1, to=99, width=3, textvariable=self.thread_count)
        self.threads_box.grid(row=0, column=1, padx=default_padding, pady=default_padding)
        tk.Label(opt_frame, text='Threads:').grid(row=0, column=0, padx=default_padding, pady=default_padding)
        opt_frame.grid(row=lv('mr'), column=lv('mc'), columnspan=3, sticky='w')
        lr('mc')
        li('mr')

        tk.Label(self, text='Filters:').grid(row=lv('mr'), column=li('mc'), columnspan=3, padx=default_padding, pady=default_padding, sticky='w')
        lr('mc')
        li('mr')

        self.filter_checks = []
        check_frame = tk.Frame(self)
        for ndx, filter_text in enumerate(self.FILTERS):
            bind = tk.BooleanVar(value=True)
            self.filter_bools.append(bind)
            check_box = tk.Checkbutton(check_frame, text=filter_text, variable=bind)
            check_box.select()
            self.filter_checks.append(check_box)
            check_box.grid(row=0, column=ndx, padx=default_padding, pady=default_padding)
        check_frame.grid(row=lv('mr'), column=li('mc'), columnspan=3, stick='w')
        lr('mc')
        li('mr')

        #other options
        tk.Label(self, text='Other pngout options:').grid(row=lv('mr'), column=li('mc'), columnspan=3, padx=default_padding, pady=default_padding, sticky='w')
        lr('mc')
        li('mr')

        pngopt_frame = tk.Frame(self)
        self.keep_pal_chk = tk.Checkbutton(pngopt_frame, text='Keep palette indicies (/kp)', variable=self.keep_pal)
        self.keep_pal_chk.grid(row=0, column=0, padx=default_padding, pady=default_padding)
        pngopt_frame.grid(row=lv('mr'), column=lv('mc'), columnspan=3, sticky='w')
        lr('mc')
        li('mr')

        #button bar
        btn_bar = tk.Frame(self)
        self.go_btn = tk.Button(btn_bar, text="Go!", command=self.start_work)
        self.go_btn.grid(row=0, column=0, padx=default_padding, pady=default_padding)
        self.stop_btn = tk.Button(btn_bar, text="Cancel", command=self.stop_work)
        self.stop_btn.config(state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, padx=default_padding, pady=default_padding)
        #self.debug_btn = tk.Button(btn_bar, text='Debug', command=self.debug_action)
        #self.debug_btn.grid(row=0, column=2, padx=default_padding, pady=default_padding)
        btn_bar.grid(row=lv('mr'), column=lv('mc'), columnspan=3, sticky='w')
        lr('mc')
        li('mr')

        #progress
        self.job_progress = ttk.Progressbar(self, maximum=1)
        self.job_progress.grid(row=lv('mr'), column=li('mc'), columnspan=3, sticky='we', padx=default_padding, pady=default_padding)
        lr('mc')
        li('mr')

        #work window
        self.png_parent = ScrollableFrame(self, borderwidth=1, relief='sunken')
        self.png_parent.canvas['borderwidth'] = 0
        self.png_parent.canvas['highlightthickness'] = 0
        self.png_parent.grid(row=lv('mr'), column=0, columnspan=3, sticky='news', padx=2, pady=2)
        self.grid_rowconfigure(lv('mr'), weight=1)
        self.grid_columnconfigure(1, weight=1)
        lr('mc')
        li('mr')

        #status bar
        self.status_bar = tk.Label(self, relief='sunken', borderwidth=1, padx=2, pady=2, anchor='w')
        self.status_bar.grid(row=lv('mr'), column=0, columnspan=2, sticky='we', padx=default_padding, pady=default_padding)
        self.time_bar = tk.Label(self, relief='sunken', borderwidth=1, padx=2, pady=2, anchor='e')
        self.time_bar.grid(row=lv('mr'), column=2, sticky='we', padx=default_padding, pady=default_padding)
        #endregion

        self.load_config()

        #window min size
        self.update_idletasks()
        self.after_idle(lambda: self.minsize(self.winfo_width(),350))

        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.update_status()
        self.update_time()

    def check_pngout_set(self) -> bool:
        #program location set in config
        if hasattr(PngUnit, 'PNGOUT_PATH') and PngUnit.PNGOUT_PATH.exists():
            return True
        #not set in config, but it's in the same directory
        trypath = Path.cwd() / 'pngout.exe'
        if trypath.exists():
            PngUnit.PNGOUT_PATH = trypath
            return True
        #ask the user where it is
        pathstr = filedialog.askopenfilename(title='Select location of pngout program', filetypes=[('pngout executable', 'pngout*')])
        if not len(pathstr):
            self.pngout_path_fail()
            return False
        path = Path(pathstr)
        if not path.exists():
            self.pngout_path_fail()
            return False
        PngUnit.PNGOUT_PATH = path
        return True
    
    def pngout_path_fail(self):
        messagebox.showerror(title='Critical Error', message='You did not provide a valid path for pngout. This is required to run the front end.')

    def thread_check(self):
        self.process_thread_events()
        self.update_time()
        #call again until we finish
        if self.current_state != self.STATE.IDLE:
            self.after(self.THREAD_CHECK_TIME, self.thread_check)

    def process_thread_events(self):
        if not hasattr(self, 'manager'):
            return
        while not self.manager.EVENT_QUEUE.empty():
            self.handle_event(self.manager.EVENT_QUEUE.get())

    #params not annotated because pylance complains, 
    #event is any child class of pngthreads.BaseEvent
    def handle_event(self, event):
        method = self.event_map.get(type(event), None)
        if method is None:
            print(f'Unhandled event type: {type(event)}')
            return
        method(event)

    def handle_start(self, event: pt.SessionStartEvent):
        self.start_time = time()
        self.end_time = 0
        self.current_state = self.STATE.RUNNING
        self.update_status()

    def handle_end(self, event: pt.SessionEndEvent):
        self.end_time = time()
        self.update_time()
        self.finish()

    def handle_queued(self, event: pt.SessionQueueEvent):
        self.add_unit(event.id, event.path)
        self.files_total += 1
        self.update_job_progress()

    def handle_unit_error(self, event: pt.PngErrorEvent):
        self.error_count += 1
        self.update_job_progress()
        uf = self.get_unit_frame(event.id)
        if uf is None:
            return
        text = event.error
        if len(event.detail):
            text += f"\n{event.detail}"
        uf.set_detail(text)
        uf.set_status('Error')

    def handle_unit_done(self, event: pt.PngDoneEvent):
        self.size_savings += event.size_change
        self.files_done += 1
        self.update_job_progress()
        uf = self.get_unit_frame(event.id)
        if uf is None:
            return
        if event.size_change == 0:
            uf.set_detail(f'No change in {event.time:0.2f} sec')
        else:
            uf.set_detail(f'{self.nice_size(event.size_change)} reduced in {event.time:0.2f} sec: {event.final_switches}')
        uf.set_status('Done')

    def handle_unit_update(self, event: pt.PngUpdateEvent):
        uf = self.get_unit_frame(event.id)
        if uf is None:
            return
        uf.update_progress(event.done, event.required)
        uf.set_status('Running')

    def open_path(self):
        result = filedialog.askdirectory(initialdir=self.path_text.get())
        if not len(result):
            return
        self.path_text.set(result)

    def start_work(self):
        #check path
        path = Path(self.path_text.get().strip(' \t\n\r\"\''))
        if not path.exists():
            self.error_message('File or directory does not exist')
            return
        if not path.is_dir() and not PngUnit.is_extension_valid(path):
            self.error_message('File is not a valid type for pngout')
            return
        #filters and check
        filters = self.get_selected_filters()
        if not len(filters):
            self.error_message('No filters selected, please select at least 1')
            return
        if not self.check_pngout_set():
            return
        self.work_path = path
        self.clear_units()
        self.stats_reset()
        self.update_job_progress()
        self.go_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        extra_switches = []
        if self.keep_pal.get():
            extra_switches.append('/kp')
        
        order = WorkOrder(
            self.thread_count.get(), 
            [self.work_path], 
            filters, 
            self.recursive.get(), 
            extra_switches)
        
        self.after(self.THREAD_CHECK_TIME, self.thread_check)
        
        self.manager = pt.Manager(order, daemon=True)
        self.manager.start()

    def stop_work(self):
        self.stop_btn.config(state=tk.DISABLED)
        self.manager.stop_event.set()
        self.current_state = self.STATE.STOPPING
        self.update_status()

    def finish(self):    
        finish_message = 'Job Canceled' if self.current_state == self.STATE.STOPPING else 'Completed'
        icon = 'warning' if self.current_state == self.STATE.STOPPING else 'info'
        self.go_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.current_state = self.STATE.IDLE
        self.thread_check() #one last time to make sure queue is empty
        self.update_status()
        message = f'{finish_message}\n\n'
        message += f'{self.files_total} files queued\n'
        message += f'{self.files_done} complete\n'
        message += f'{self.error_count} errors\n'
        message += f'{self.nice_size(self.size_savings)} reduced total'
        messagebox.showinfo(title="Final Stats", icon=icon, message=message)

    def stats_reset(self):
        self.files_done = 0
        self.files_total = 0
        self.size_savings = 0
        self.error_count = 0

    def add_unit(self, id: int, path: Path):
        display_name = str(path.relative_to(self.work_path)) if self.work_path.is_dir() else str(path.name)
        uf = UnitFrame(self.png_parent.scrollable_frame, 0, display_name, borderwidth=1, relief='solid', padding=(2,2))
        self.units[id] = uf
        uf.pack(padx=2, pady=2, fill='x', expand=True)

    def clear_units(self):
        self.units.clear()
        self.png_parent.clear()

    def get_unit_frame(self, id: int) -> UnitFrame | None:
        uf = self.units.get(id, None)
        #debug
        if uf is None:
            print(f"Unit frame does not exist for {id}")
        return uf

    def load_config(self):
        if not self.CONFIG_PATH.exists():
            return
        try:
            with open(self.CONFIG_PATH, 'r') as fp:
                config = json.load(fp)
                self.keep_pal.set(config['keep_pal'])
                self.recursive.set(config['recursive'])
                self.thread_count.set(config['thread_count'])
                PngUnit.PNGOUT_PATH = Path(config['pngout_path'])
                for ndx, var in enumerate(self.filter_bools):
                    var.set(ndx in config['filters'])
        except Exception:
            self.warning_message('Configuration file could not be read. Some defaults might be used.')

    def save_config(self):
        try:
            config = {
                'pngout_path': str(PngUnit.PNGOUT_PATH),
                'recursive': self.recursive.get(),
                'keep_pal': self.keep_pal.get(),
                'thread_count': self.thread_count.get(),
                'filters': self.get_selected_filters()
            }
            with open(self.CONFIG_PATH, 'w') as fp:
                json.dump(config, fp)
        except Exception as e:
            #since this is called on program close
            pass

    def warning_message(self, message: str):
        messagebox.showwarning('Warning', message)

    def error_message(self, message: str):
        messagebox.showerror('Error', message)

    def get_selected_filters(self) -> list[int]:
        return [ ndx for ndx, bind in enumerate(self.filter_bools) if bind.get() ]

    def on_close(self):
        if self.current_state != self.STATE.IDLE:
            if not messagebox.askyesno(title='Confirm Exit', message='Are you sure you want to quit while a job is running?'):
                return
        self.save_config()
        self.quit()

    def update_job_progress(self):
        if self.files_total > 0:
            self.job_progress['value'] = (self.files_done + self.error_count) / self.files_total
            return
        self.job_progress['value'] = 0

    def update_time(self):
        self.time_bar.config(text=self.get_time_diff())

    def update_status(self):
        self.status_bar.config(text=self.get_state_message())

    def get_state_message(self) -> str:
        match self.current_state:
            case self.STATE.IDLE:
                return 'Ready'
            case self.STATE.RUNNING:
                return 'Running...'
            case self.STATE.STOPPING:
                return 'Waiting for threads to stop...'
            case _:
                return ''

    def get_time_diff(self) -> str:
        if self.start_time == 0 and self.end_time == 0:
            return '00:00:00'
        if self.end_time == 0:
            total = time() - self.start_time
        else:
            total = self.end_time - self.start_time
        
        hours, remain = divmod(total, 3600)
        mins, seconds = divmod(remain, 60)
        
        return f'{int(hours):02}:{int(mins):02}:{int(seconds):02}'
    
    def nice_size(self, bytes: int) -> str:
        #only 3 paths, no need for iteration
        if bytes < 1024:
            return f'{bytes} bytes'
        kb = 1024
        mb = kb * 1024
        if bytes < mb:
            return f'{bytes / kb:0.2f} Kb'
        mb = kb * 1024
        return f'{bytes / mb:0.2f} Mb'
    
    '''
    def debug_action(self):
        print(PngUnit.PNGOUT_PATH)
    '''