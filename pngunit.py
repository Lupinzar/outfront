from pathlib import Path
from time import time
import subprocess
from typing import ClassVar
from dataclasses import dataclass

type FilterList = list[int]
type SwitchList = list[str]

_VALID_EXTENSIONS: list[str] = [
    '.png',
    '.jpg',
    '.gif',
    '.tga',
    '.pcx',
    '.bmp'
]

@dataclass
class WorkOrder:
    threads: int
    paths: list[Path]
    filters: FilterList
    recursive: bool
    extra_switches: SwitchList

class PngUnitException(Exception):
    def __init__(self, message: str, detail: str=''):
        super().__init__(message)
        self.detail = detail

class PngUnit:
    PNGOUT_PATH: ClassVar[Path]
    COLOR_SEARCH: ClassVar[str] = '; try /c'
    ID_COUNTER: ClassVar[int] = 0
    def __init__(self, path: Path, filters: FilterList, extra_switches: SwitchList = []):
        self.id = self.get_new_id()
        self.path = path
        self.type = path.suffix.lower()
        self.size = path.stat().st_size
        self.final_size = self.size
        self.time_start: float
        self.time_end: float
        self.color_number: int = 0
        self.color_adjusted: bool = False
        self.converted: bool = False
        self.filters = filters
        self.filters_left = filters.copy()
        self.extra_switches = extra_switches
        self.final_switches: str = ''

    def run_pass(self) -> bool:
        if not len(self.filters_left):
            return False
        current_filter = self.filters_left.pop(0)
        result = subprocess.run(self.build_command(current_filter), capture_output=True, text=True)
        if result.returncode in [0,2]:
            if not self.is_png() and not self.converted:
                self.converted = True
            return True
        if result.returncode == 3:
            #prevent an infinite loop if we unexpectedly reach this return code again after adjustment
            if self.color_adjusted:
                raise PngUnitException('Bad command error after color adjustment', result.stdout.strip())
            self.adjust_color(result.stdout)
            self.filters_left.insert(0, current_filter) #try this filter again
            return True
        raise PngUnitException('Error running pngout', result.stdout.strip())
    
    def is_png(self) -> bool:
        return self.type == '.png'
    
    def already_converted(self) -> bool:
        if self.is_png():
            return False
        con_file = self.make_output_path()
        return con_file.exists()
    
    def start_stats(self):
        self.time_start = time()

    def end_stats(self):
        self.time_end = time()
        self.final_size = self.make_output_path().stat().st_size
        self.final_switches = self.get_final_switches()

    def get_final_switches(self) -> str:
        result = subprocess.run([str(PngUnit.PNGOUT_PATH), str(self.make_output_path()), '/l'], capture_output=True, text=True)
        if result.returncode:
            return "Unknown"
        return result.stdout.strip()
    
    def adjust_color(self, output: str):
        try:
            found = output.index(PngUnit.COLOR_SEARCH)
            start = found + len(PngUnit.COLOR_SEARCH)
            self.color_number = int(output[start:start+1])
            self.color_adjusted = True
        except Exception as e:
            raise PngUnitException('Could not determine recommended color depth number', str(e))
    
    def build_command(self, filter: int) -> list[str]:
        parts = [str(PngUnit.PNGOUT_PATH)]
        if not self.is_png() and not self.converted:
            #if it's not a png and we haven't converted, build 
            #command to convert on first run
            parts.append(str(self.path))
            parts.append(str(self.make_output_path()))
        else:
            parts.append(str(self.make_output_path()))
        parts.append(f'/c{self.color_number}')
        parts.append(f'/f{filter}')
        parts.append('/y')
        return parts + self.extra_switches
    
    def make_output_path(self) -> Path:
        if not self.is_png():
            return self.path.parent / f'{self.path.stem}.png'
        return self.path
    
    def get_pass_total(self) -> int:
        return len(self.filters)
    
    def get_pass_done(self) -> int:
        return len(self.filters) - len(self.filters_left)
    
    @staticmethod
    def is_extension_valid(path: Path) -> bool:
        return path.suffix.lower() in _VALID_EXTENSIONS
    
    @classmethod
    def get_new_id(cls) -> int:
        new = cls.ID_COUNTER
        cls.ID_COUNTER += 1
        return new