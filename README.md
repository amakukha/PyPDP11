## PyPDP11
PDP-11 emulator for Python 3 with GUI. 

It runs the Version 6 Unix operating system (1975), the code of which was famously covered by *A Commentary on the Unix Operating System* (1976) by John Lions.

This project is based on [Julius Schmidt's PDP-11 emulator](http://pdp11.aiju.de) for JavaScript, which you can run in a browser.

Example screenshot:
<p align="center">
  <img
  src="https://github.com/amakukha/PyPDP11/raw/master/screenshots/PDP-11_emulator_for_Python_GUI_screenshot.png"
  width="250" alt="PDP-11 emulator for Python 3. This image of Version 6 Unix still retained /usr/ken directory belonging to Ken Thompson, albeit an empty one.">
</p>

## Prerequisites

 - Python 3
 
NOTE: make sure Python 3 is installed with Tcl version 8.6 or later (especially if you are using MacOS):
```
python3 -c 'import tkinter; print(tkinter.TclVersion)'
```

## Usage

  1. Run the `pdp11.py` file with Python. A console window should appear.
  2. Type `unix` and press Enter to run the OS.

## Note

Unix V6 used `chdir` command instead of `cd`.

Run `stty -lcase` to enable lowercase output.

## What's new
Compared to the original JavaScript code, this implementation has the following benefits:
 - pasting text into the terminal from clipboard is allowed (making it much more usable)
 - resource friendlier `WAIT` instruction (not overheating the physical CPU)
 - faster output 

In the near future, it will also allow saving the disk state as well as importing and exporting
files between Unix V6 and your machine.

## Known bugs
Help is welcome on the following issues:
 - CPU emulator is even slower than the JavaScript counterpart
 - characters don't always update on screen in the terminal, especially after a lengthy output from
   the OS
