## PyPDP11
PDP-11 emulator for Python 3 with GUI. 

It runs the Version 6 Unix operating system (1975), the code of which was famously covered by *A Commentary on the Unix Operating System* (1976) by John Lions.

This code is a translation of [Julius Schmidt's PDP-11 emulator](http://pdp11.aiju.de) for JavaScript, which you can run in a browser.

Example screenshot:
<p align="center">
  <img
  src="https://github.com/amakukha/PyPDP11/raw/master/screenshots/PDP-11_emulator_for_Python_GUI_screenshot.png"
  width="250" alt="PDP-11 emulator for Python 3. This image of Version 6 Unix still retained /usr/ken directory belonging to Ken Thompson, albeit an empty one.">
</p>

## Prerequisites

 - Python 3
 - make sure Python 3 is installed with Tcl version 8.6 or later (especially if you are using MacOS)

## Usage

  1. Run the `pdp11.py` file with Python. A console window should appear.
  2. Type `unix` and press Enter to run the OS.

## Note

Unix V6 used `chdir` command instead of `cd`.

Run `stty -lcase` to enable lowercase output.
