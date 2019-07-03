#!/usr/bin/env python3

# This code is based on Julius Schmidt's PDP-11 emulator for JavaScript.
# You can run that one in your browser: http://pdp11.aiju.de
# Many new features were added to the terminal logic, particularly start routine and ability to
# paste text from clipboard.
# (c) 2011, Julius Schmidt, JavaScript/HTML implementation, MIT License
# (c) 2019, Andriy Makukha, ported to Python 3, MIT License
# Version 6 Unix (in the disk image) is available under the four-clause BSD license.

import time, threading, queue
from interrupt import Interrupt
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font as tkfont
import tkinter.scrolledtext as scrolledtext

AUTOSTART_TIMEOUT_S = 15    # how many seconds to wait for user input before loading Unix automatically?
GUI_MSPF = 50               # milliseconds per "frame"

def ostr(d, n=6):
    return '{{:0{}o}}'.format(n).format(d)

EAST_WEST = tk.E + tk.W
NORTH_SOUTH = tk.N + tk.S
ALL_SIDES = EAST_WEST + NORTH_SOUTH

class ReadOnlyText(scrolledtext.ScrolledText):

    MAX_LINES = 10000

    def __init__(self, master, *args, **kargs):
        super().__init__(*args, **kargs)
        self.master = master
        self.config(state=tk.DISABLED)
        self.lock = threading.Lock()        # probably not needed

    def println(self, text):
        self.print(text + '\n')

    def print(self, text):
        self.lock.acquire()
        self.config(state=tk.NORMAL)
        lines = float(self.index(tk.END))
        if lines >= self.MAX_LINES:
            self.delete(1.0, lines - self.MAX_LINES)
        self.insert(tk.END, text)
        self.config(state=tk.DISABLED)
        self.see(tk.END)
        self.lock.release()

    def clear(self):
        self.lock.acquire()
        self.config(state=tk.NORMAL)
        lines = float(self.index(tk.END))
        self.delete(1.0, lines)
        self.config(state=tk.DISABLED)
        self.see(tk.END)
        self.lock.release()
        

class Terminal(ttk.Frame):
    def __init__(self, system):
        if tk.TclVersion < 8.6:
            print('WARNING: your Tcl version %s is too old', tkinter.TclVersion)
        super(Terminal, self).__init__(None)
        self.keybuff_lock = threading.Lock()
        self.queue = queue.Queue()          # events to be processed by GUI
        self.debug_queue = queue.Queue()    # debug messages to be shown TODO
        self.meta_pressed = False
        self.control_pressed = False
        self.start_commands = []            # additional start commands

        self.TKS = 0
        self.TPS = 0
        self.keybuf = 0
        self.pastebuff = []
        self.system = system
        
        # GUI little features
        self.manual_start = True        # started manually or with "Start routine"?
        self.first = ''                 # first command entered by user; None - don't track (for showing the "unix" hint)
        self.last_printed = ''          # last three characters printed by OS
        self.prompt_cnt = 0             # how many times OS outputed prompt
        self.ips = 0

        self.grid()
        self.createWidgets()

        self.master.after(GUI_MSPF, self.process_queue)
        self.master.after(AUTOSTART_TIMEOUT_S*1000, self.autostart)
        self.master.after(1000, self._show_ips)

    def createWidgets(self):
        font = tkfont.Font(family='Courier New', size=15)
        style = ttk.Style()
        #style.configure('.', font=font)

        # Center frame 
        #self.center = tk.Frame(self, bd=2, relief=tk.SUNKEN)
        self.center = ttk.Frame(self)
        self.center.grid(row=0, sticky=EAST_WEST)
        #self.center.grid_rowconfigure(0, weight=1)
        #self.center.grid_columnconfigure(0, weight=1)

        self.console = ReadOnlyText(self.master, self.center, height = 25, width = 89, fg='#04fe7c',
                                    bg='#292929', font = ('Courier New', 15))
        self.console.grid(row=0, column=0, sticky=ALL_SIDES)
        self.console.bind('<KeyPress>', self.key_press)
        self.console.bind('<KeyRelease>', self.key_release)
        self.console.bind('<Button-1>', self.console_focus)
        self.console.bind('<Double-Button-1>', self.console_focus)
        self.console.focus_set()

        self.debug = ReadOnlyText(self.master, self.center, height = 5, width = 89, font = ('Courier New', 13), relief=tk.SUNKEN)
        self.debug.grid(row=1, column=0, sticky=ALL_SIDES)

        self.bottom = ttk.Frame(self)
        self.bottom.grid(row=2, sticky=tk.W)
        self.ips_label = tk.Label(self.bottom, text='', font=font, relief=tk.SUNKEN, width = 11)
        self.ips_label.grid(row=0, column=0, sticky=tk.W)
        self.ctrl_label = tk.Label(self.bottom, text='ctrl', font=font, relief=tk.SUNKEN, width=5)
        self.ctrl_label.grid(row=0, column=1, sticky=tk.W)
        self.start_button = tk.Button(self.bottom, text='Start routine', command=self.start)
        self.start_button.grid(row=0, column=2, sticky=tk.W)
        self.extract_button = tk.Button(self.bottom, text='Extract', command=self.extract_image)
        self.extract_button.grid(row=0, column=3, sticky=tk.W)
        self.load_button = tk.Button(self.bottom, text='Load', command=self.load_image)
        self.load_button.grid(row=0, column=4, sticky=tk.W)
        self.sync1_label = ttk.Label(self.bottom, text='Unix V6:')
        self.sync1_label.grid(row=0, column=5, sticky=tk.W)
        self.sync1_entry = ttk.Entry(self.bottom, text='/usr/pub', width=9)
        self.sync1_entry.grid(row=0, column=6, sticky=tk.W)
        self.sync1_entry.insert(0, '/usr/pub')
        self.sync2_label = ttk.Label(self.bottom, text='Local:')
        self.sync2_label.grid(row=0, column=7, sticky=tk.W)
        self.sync2_entry = ttk.Entry(self.bottom, text='data', width=9)
        self.sync2_entry.grid(row=0, column=8, sticky=tk.W)
        self.sync2_entry.insert(0, './data')
        self.sync_button = tk.Button(self.bottom, text='Sync', command=self.sync)
        self.sync_button.grid(row=0, column=9, sticky=tk.W)
    
    def console_focus(self, event):
        # Triggered by click or double-click
        self.console.focus_set()

    def autostart(self):
        # Triggered by timer
        if self.first == '':
            self.manual_start = False
            self.debug.println("Autostart (waiting in the boot screen eats up CPU cycles).")
            self.start_commands += ['date\n']
            self.start_routine()

    def start(self):
        # Button "Start"
        self.manual_start = False
        self.start_routine()

    def start_routine(self):
        if self.prompt_cnt == 0:
            self.paste('unix\n')
            self.first = None       # don't show the "type unix" hint
            self.debug.println("Start routine loads UNIX for you and configures terminal to allow lowercase letters.")
        elif self.prompt_cnt-2>=0 and self.prompt_cnt-2<len(self.start_commands):
            self.paste(self.start_commands[self.prompt_cnt-2])
        else:
            self.paste('stty -lcase\n')

    def extract_image(self):
        # Button "Extract"
        self.system.interrupt(Interrupt.ExtractImage, 1)

    def load_image(self):
        # Button "Load"
        self.system.interrupt(Interrupt.LoadImage, 1)

    def sync(self):
        # Bytton "Sync"
        self.system.unix_dir = self.sync1_entry.get()
        self.system.local_dir = self.sync2_entry.get()
        self.system.interrupt(Interrupt.Synchronize, 1)

    def paste(self, what=''):
        if not what:
            what = self.master.clipboard_get()
        if not what:
            self.debug.println("Clipboard is empty, nothing to paste.")
            return
        clipboard = [ord(c) for c in what]
        clipboard = [c for c in clipboard if c<256]
        if not clipboard:
            return
        self.keybuff_lock.acquire()
        self._addchar(clipboard.pop(0))
        self.pastebuff.extend(clipboard)
        self.keybuff_lock.release()

    def update_ctrl(self):
        self.ctrl_label.config(text={
            (False,False): 'ctrl',
            (True, False): 'CTRL',
            (False, True): 'COMM',
            (True,  True): 'CT+CO',
        }[(self.control_pressed, self.meta_pressed)])

    def key_release(self, event):
        if event.keysym in ['Meta_L', 'Control_L']:
            if event.keysym == 'Meta_L':
                self.meta_pressed = False
            elif event.keysym == 'Control_L':
                self.control_pressed = False
            self.update_ctrl()
    
    def key_press(self, event):
        if event.keysym in ['Meta_L', 'Control_L']:
            if event.keysym == 'Meta_L':
                self.meta_pressed = True
            elif event.keysym == 'Control_L':
                self.control_pressed = True
            self.update_ctrl()
        ch = event.char
        if len(ch)==1 and ord(ch)<256:

            # Process input to show the hint
            if ch == '\r': ch = '\n' # TODO: will it work on Windows?
            if self.first != None:
                if ch == '\n':
                    if self.first != 'unix':
                        self.console.println("")
                        self.console.println("hint: type \"unix\" command to run Unix V6")
                    self.first = None
                else:
                    self.first += ch

            # Handle the Ctrl+C / Ctrl+V properly
            if ch in 'c\x03' and (self.control_pressed or self.meta_pressed) and self.console.tag_ranges(tk.SEL):
                selection = self.console.selection_get()
                self.master.clipboard_clear()
                self.master.clipboard_append(selection)
                self.writedebug('Selection copied to clipboard.\n')
                self.console.tag_remove(tk.SEL, "1.0", tk.END)
                print ('Deleted selection')
                return
            if ch == '\x03': print('Ctrl+C')
            if ch in 'v\x16' and (self.control_pressed or self.meta_pressed):
                self.writedebug('Pasted from clipboard.\n')
                self.paste()
                return
            if ch == '\x03': print('Ctrl+V')

            #  Pass the character to the OS
            self.keybuff_lock.acquire()
            self._addchar(ord(event.char))
            self.keybuff_lock.release()

    def cleardebug(self):
        # TODO: use queue
        self.debug.clear()

    def clear(self):        # terminal
        # TODO: use queue
        # Clear terminal screen
        #var len = document.getElementById("terminal").firstChild.nodeValue.length;
        #document.getElementById("terminal").firstChild.deleteData(0, len);
        self.console.clear()

        self.TKS = 0
        self.TPS = 1<<7
        self.T = None

    def writedebug(self, msg):
        # This is called by the CPU thead
        self.debug.print(msg)
        self.master.update_idletasks()

    def process_queue(self):
        # This is called by the GUI thread
        if not self.queue.empty():
            message = ''
            while not self.queue.empty():
                ch = self.queue.get()
                if ch in '\r\x7f':          # ignored characters
                    continue
                if ord(ch)<32 and ch!='\n' or ord(ch)>126:
                    ch = repr(ch)[1:-1]     # Python-style escaping
                message += ch
                if len(message)>=80:        # avoid cycling here for too long without update
                    break
            # Add text to the terminal
            self.console.print(message)
            self.master.update_idletasks()
        self.master.after(GUI_MSPF, self.process_queue)

    def add_to_write_queue(self, msg):   # terminal
        # This is called by the CPU thread
        self.queue.put(msg)
        self.last_printed = self.last_printed[-1:]+msg 
        if self.last_printed == '# ':
            self.prompt_cnt += 1
            if self.prompt_cnt < 2+len(self.start_commands) and not self.manual_start:
                self.start()

    def _addchar(self, c):
        # This is called by the GUI thread
        self.TKS |= 0x80
        self.keybuf = c
        if self.TKS & (1<<6):
            self.system.interrupt(Interrupt.TTYIN, 4)

#    def _specialchar(self, c):
#        # TODO: onkeyup="specialchar(event.which)"
#        if c == 42:     # '*'
#            self.keybuf = 4
#        elif c == 19:   # 0x13
#            self.keybuf = 0o34
#        elif c == 46:   # '.'  // EOF?
#            self.keybuf = 127
#        else:
#            return
#        self.TKS |= 0x80
#        if self.TKS & (1<<6):
#            self.system.interrupt(Interrupt.TTYIN, 4)

    def _getchar(self):
        # This is in the CPU thread, but can modify buffers, therefore a lock is needed
        c = 0
        self.keybuff_lock.acquire()
        if self.TKS & 0x80:
            self.TKS &= 0xff7e
            c = self.keybuf
            if self.pastebuff:
                self._addchar(self.pastebuff.pop(0))
        self.keybuff_lock.release()
        return c

    def consread16(self, a):
        # This is called by the CPU thread
        if a == 0o777560:
            self.keybuff_lock.acquire()
            TKS = self.TKS
            self.keybuff_lock.release()
            return TKS
        elif a == 0o777562:
            return self._getchar()
        elif a == 0o777564:
            self.keybuff_lock.acquire()
            TPS = self.TPS
            self.keybuff_lock.release()
            return TPS
        elif a == 0o777566:
            return 0
        self.system.panic("read from invalid address " + ostr(a,6))

    def conswrite16(self, a, v):
        # This is called by the CPU thread
        if a == 0o777560:
            if v & (1<<6):
                self.TKS |= 1<<6
            else:
                self.TKS &= ~(1<<6)
        elif a == 0o777564:
            if v & (1<<6):
                self.TPS |= 1<<6
            else:
                self.TPS &= ~(1<<6)
        elif a == 0o777566:
            v &= 0xFF       # TODO: why does it send '0x8D' sometimes?
            if not (self.TPS & 0x80):
                return
            if v == 13:     # ignoring '\r'
                return
            else: 
                self.add_to_write_queue(chr(v & 0x7F))
            self.TPS &= 0xff7f
            if self.TPS & (1<<6):
                #//setTimeout("TPS |= 0x80; interrupt(INTTTYOUT, 4);", 1);
                self.TPS |= 0x80
                self.system.interrupt(Interrupt.TTYOUT, 4)
            else:
                #//setTimeout("TPS |= 0x80;", 1);
                self.TPS |= 0x80
        else:
            system.panic("write to invalid address " + ostr(a,6));

    def _show_ips(self):
        self.ips_label.config(text='IPS ={:-4.0f}K'.format(self.ips/1000))
        self.master.after(1000, self._show_ips)
