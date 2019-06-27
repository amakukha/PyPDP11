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
 
Make sure Python 3 is installed with Tcl version 8.6 or later (especially if you are using MacOS).
To check:
```
python3 -c 'import tkinter; print(tkinter.TclVersion)'
```

## Usage

  1. Run the file `pdp11.py` with Python.
  2. Press button `Start routine` to run the OS.

## Note

Unix V6 used `chdir` instead of `cd`. Issuing command `stty -lcase` is needed to enable lowercase output.

## What's new
Compared to the original JavaScript code, this implementation has the following benefits:
 - pasting text into the terminal from clipboard is allowed (making it much more usable)
 - resource friendlier `WAIT` instruction (not overheating the physical CPU)
 - faster output 

In the near future, it will also allow saving the disk state as well as importing and exporting
files between Unix V6 and your machine.

## Where are the manuals?
The image included into this repository misses on
[sources](https://github.com/eunuchs/unix-archive/tree/master/PDP-11/Trees/V6/usr/source),
[manual pages](https://github.com/eunuchs/unix-archive/tree/master/PDP-11/Trees/V6/usr/man) and
[documentation](https://github.com/eunuchs/unix-archive/tree/master/PDP-11/Trees/V6/usr/doc).
It is unsurprising, knowing that RK05 could only contain around 2.5 MB of data, while the Unix V6
sources alone measure beyond that capacity.
