# outfront a pngout Front End

This is a simple python and tkinter front end for
Ken Silverman's pngout. I mostly wrote this as
an exercise to see if tkinter was worth while (no)
and to play with uv and nuitka. Although this is
mostly for personal use, you are free to use and
expand upon it.

# Install

First, make sure you have a binary for pngout.

Windows: https://advsys.net/ken/utils.htm
Linux / Unix: https://www.jonof.id.au/kenutils.html

This project can be run with uv or a globally installed 
python. There aren't any dependancies outside of the
standard library. uv is useful if you want to
build an executable with nuitka. There are options
embedded in `outfront.py` for nuitka.

System/global python:
`python outfront.py`

uv:
`uv run outfront.py`

nuitka build:
`uvx --with imageio --from nuitka nuitka outfront.py`

# Other Considerations

For Windows users you can place the pngout.exe binary
in the same folder as the `outfront.py` script or
the program will ask you where it lives the first
time you try to start a batch.

It's only been tested on Windows so far. I will try
to get around to a Linux test eventually.

Hope to provide nuitka built releases as soon as I
can get some milage with the front end.