## PyPDP11
PDP-11 emulator in Python 3 with GUI. 

It runs the Version 6 Unix operating system (1975), the code of which was famously covered by *A Commentary on the Unix Operating System* (1976) by John Lions.

This project is based on [Julius Schmidt's PDP-11 emulator](http://pdp11.aiju.de) in JavaScript, which you can run in a browser.

Example screenshots:
<p align="center">
  <img
  src="https://github.com/amakukha/PyPDP11/raw/master/screenshots/Ken_Thompson_chess_1975_Unix_V5_PDP-11_emulator_for_Python_screenshot.png"
  width="225" alt="PDP-11 emulator for Python 3. Playing with Ken Thompson's chess implementation in Version 6 Unix (1975).">
  <img
  src="https://github.com/amakukha/PyPDP11/raw/master/screenshots/Syncing_directory_PDP-11_emulator_Python_GUI_screenshot.png"
  width="225" alt="PDP-11 emulator for Python 3. Syncing directory between Unix V6 and local filesystems.">
  <img
  src="https://github.com/amakukha/PyPDP11/raw/master/screenshots/TMG_in_TMGL_Doug_McIlroy_PDP-11_emulator_for_Python_screenshot.png"
  width="225" alt="PDP-11 emulator for Python 3. Viewing code of Doug McIlroy's TMG in TMGL for Unix V6.">
</p>

## Prerequisites

 - Python 3.5+
 
Make sure Python 3 is installed with Tcl version 8.6 or later (especially if you are using MacOS).
To check:
```
python3 -c 'import tkinter; print(tkinter.TclVersion)'
```

## Usage

  1. Run the file `pdp11.py` with Python.
  2. Press button `Start routine` to run the OS. This will start the [Unix shell](https://en.wikipedia.org/wiki/Unix_shell).

Additional usage notes: 
  - Instead of `cd`, Unix V6 shell used `chdir` command. 
  - Issuing command `stty -lcase` is needed to enable lowercase output. (In case you are wondering.)
  - Instead of `Ctrl+C`, press Backspace button if you want to halt execution of a program.
  - If you want to export the disk image for whatever reason, don't forget to execute the `sync` command first (it flushes the delayed I/O to disk).

## What's new
Compared to the original JavaScript code, this implementation has the following benefits:
 - pasting text into the terminal from clipboard is allowed (making it much more usable)
 - resource friendlier `WAIT` instruction (not overheating the physical CPU)
 - syncing a directory between Unix V6 and your machine
 - saving and loading the disk state
 - faster output 
 - some commands were backported and included into the image (see [tools](https://github.com/amakukha/PyPDP11/tree/master/tools) directory)

## Where are the manuals?
The disk image included into this repository misses on most
[sources](https://github.com/eunuchs/unix-archive/tree/master/PDP-11/Trees/V6/usr/source),
[man pages](https://github.com/eunuchs/unix-archive/tree/master/PDP-11/Trees/V6/usr/man) and
[documentation](https://github.com/eunuchs/unix-archive/tree/master/PDP-11/Trees/V6/usr/doc).
It is unsurprising, knowing that RK05 disk could only contain around 2.5 MB of data, while the
Unix V6 sources alone measure beyond that capacity.

Complete Unix V6 manual in somewhat searchable PDF can be found
[here](https://ia800600.us.archive.org/19/items/v6-manual/v6-manual.pdf).

## How does syncing work?

The syncing function allows you to synchronize a folder between your working OS and the emulated Unix V6. For this purpose, modification time of files is used to track changes between synchronized directories. 

Because Unix V6 does not support modern dates, lower 24 bits of modtime in Unix V6 filesystem are used for current local time. Higher 8 bits are used to mark that files were synced. Files are considered in sync if their modification time (24 bits of it) match within 1 minutes. Any synced files within Unix V6 filesystem will appear as having modification year of 1983.

To perform syncing, the emulator compares local directory with a Unix V6 directory finding pairs of files with the same name. When a file or subdirectory exists in one filesystem, but not in the other, it is simply created where it is absent. When an unsynchronized pair of files is observed, the following actions are taken:
 - if the files were never synchronized before, they are *downloaded*: copied from Unix V6 into local directory
 - if the files were modified inside Unix V6, they are also downloaded
 - if the files were modified locally and were synced to Unix V6 more than a minute ago, they are *uploaded*: copied from local directory to Unix V6 

The emulator can synchronize files both before Unix V6 is loaded and after. When Unix V6 is not running (in the boot screen), the RK05 disk image is accessed and manipulated directly.

When Unix V6 is running, at first, the GUI issues a `sync` command, forcing the OS to flush any delayed I/O to disk. After that, the synchronized Unix directory is compared to a local directory via direct access to the disk image. All necessary changes on the Unix side are then performed via executing commands in the Unix terminal. This can be time-consuming, so be patient and don't press any buttons until syncing completes.

## Why did I write this project?

This emulator was used to restore Doug McIlroy's [TMG](https://github.com/amakukha/tmg) compiler-compiler. I ported TMG from PDP-11 assembly to modern C. I used this emulator for compile the original assembly code and run it, making sure my port functions the same way as the original.

## Wishlist

This project was used successfully, but only on MacOS. If you are willing to help, please, let me know if it runs on Linux and/or Windows.
