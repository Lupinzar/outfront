from threading import Thread, Event
from queue import Queue, Empty
from time import sleep
from pathlib import Path
from typing import ClassVar
from pngunit import PngUnit, PngUnitException, WorkOrder


#Events, put in a class queue
class BaseEvent:
    pass

class PngUpdateEvent(BaseEvent):
    def __init__(self, id: int, done: int, required: int):
        self.id = id
        self.done = done
        self.required = required

class PngErrorEvent(BaseEvent):
    def __init__(self, id: int, error: str, detail: str = ''):
        self.id = id
        self.error = error
        self.detail = detail

class PngDoneEvent(BaseEvent):
    def __init__(self, id: int, size_change: int, time: float, final_switches: str):
        self.id = id
        self.size_change = size_change
        self.time = time
        self.final_switches = final_switches

class SessionStartEvent(BaseEvent):
    pass

class SessionEndEvent(BaseEvent):
    pass

class SessionQueueEvent(BaseEvent):
    def __init__(self, id: int, path: Path):
        self.id = id
        self.path = path

#worker threads
class PngWorker(Thread):
    WORK_QUEUE: ClassVar[Queue[PngUnit]] = Queue()
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stop_event = Event()
        self.done_event = Event()

    def run(self):
        while not self.done_event.is_set():
            #print('worker: waiting for work')
            try:
                unit = self.WORK_QUEUE.get(timeout=0.2)
            except Empty:
                continue
            #TODO unhandled

            #print('got work')
            try:
                if unit.already_converted():
                    Manager.EVENT_QUEUE.put(PngErrorEvent(unit.id, 'Skipping because output PNG already exists, it may have already been converted.'))
                    continue
                unit.start_stats()
                Manager.EVENT_QUEUE.put(PngUpdateEvent(unit.id, unit.get_pass_done(), unit.get_pass_total()))
                while unit.run_pass():
                    Manager.EVENT_QUEUE.put(PngUpdateEvent(unit.id, unit.get_pass_done(), unit.get_pass_total()))
                    if self.stop_event.is_set():
                        #print('bailing due to stop')
                        return
                unit.end_stats()
                total = unit.time_end - unit.time_start
                change =  unit.size - unit.final_size
                self.WORK_QUEUE.task_done()
                Manager.EVENT_QUEUE.put(PngDoneEvent(unit.id, change, total, unit.final_switches))
            except PngUnitException as e:
                self.WORK_QUEUE.task_done()
                Manager.EVENT_QUEUE.put(PngErrorEvent(unit.id, str(e), e.detail))
            except Exception as e:
                self.WORK_QUEUE.task_done()
                Manager.EVENT_QUEUE.put(PngErrorEvent(unit.id, 'Unexpected Exception', str(e)))
        #print('exit due to done flag')
    def done(self):
        self.done_event.set()

    def stop(self):
        self.done_event.set()
        self.stop_event.set()

class Manager(Thread):
    EVENT_QUEUE: ClassVar[Queue[BaseEvent]] = Queue()
    def __init__(self, workorder: WorkOrder, **kwargs):
        super().__init__(**kwargs)
        self.workers: list[PngWorker]
        self.stop_event = Event()
        self.workorder = workorder

    def run(self):
        wo = self.workorder
        PngWorker.WORK_QUEUE = Queue() #incase we ran before and stopped mid-run
        self.EVENT_QUEUE.put(SessionStartEvent())
        self.create_workers(wo.threads)
        self.process_paths(wo)
        while not PngWorker.WORK_QUEUE.empty():
            if self.stop_event.is_set():
                break
            sleep(0.1)
        #print('manager: exit quque loop')
        self.stop_workers()
        #print('manager: stop workers sent')
        self.wait_for_workers()
        #print('manager: workers stopped')
        self.EVENT_QUEUE.put(SessionEndEvent())
        #print('queue sent')

    def process_paths(self, wo: WorkOrder):
        for path in wo.paths:
            if wo.recursive and path.is_dir:
                self.process_path_walk(path, wo)
            else:
                self.process_path_flat(path, wo)
    
    def process_path_flat(self, path: Path, wo: WorkOrder):
        if path.is_file() and PngUnit.is_extension_valid(path):
            self.enqueue_unit(PngUnit(path, wo.filters, wo.extra_switches))
            return
        for child in path.iterdir():
            if self.stop_event.is_set():
                return
            if not child.is_file():
                continue
            if not PngUnit.is_extension_valid(child):
                continue
            self.enqueue_unit(PngUnit(child, wo.filters, wo.extra_switches))

    def process_path_walk(self, path: Path, wo: WorkOrder):
        for base, dirs, files in path.walk():
            for file in files:
                if self.stop_event.is_set():
                    return
                full = base / file
                if full.is_file() and PngUnit.is_extension_valid(full):
                    self.enqueue_unit(PngUnit(full, wo.filters, wo.extra_switches))
    
    def enqueue_unit(self, unit: PngUnit):
        self.EVENT_QUEUE.put(SessionQueueEvent(unit.id, unit.path))
        PngWorker.WORK_QUEUE.put(unit)

    def create_workers(self, number: int):
        self.workers = []
        for _ in range(number):
            worker = PngWorker(daemon=True)
            self.workers.append(worker)
            worker.start()

    def stop_workers(self):
        for worker in self.workers:
            if self.stop_event.is_set():
                worker.stop()
            else:
                worker.done()

    def wait_for_workers(self):
        for worker in self.workers:
            worker.join()

    def stop(self):
        """Sends a soft stop to the thread and any active workers.
        
        Threads will exit when they next have a chance.
        """
        self.stop_event.set()