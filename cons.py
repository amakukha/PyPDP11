#!/usr/bin/env python3

# This code is based on Julius Schmidt's PDP-11 emulator for JavaScript.
# You can run that one in your browser: http://pdp11.aiju.de
# Many new features were added to the terminal logic, particularly start routine and ability to
# paste text from clipboard.
# (c) 2011, Julius Schmidt, JavaScript/HTML implementation, MIT License
# (c) 2019, Andriy Makukha, ported to Python 3, MIT License
# Version 6 Unix (in the disk image) is available under the four-clause BSD license.

import time, threading
from interrupt import Interrupt
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font as tkfont
import tkinter.scrolledtext as scrolledtext

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
        #print("print = ", repr(text))
        if text == '\r': return
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

        self.TKS = 0
        self.TPS = 0
        self.keybuf = 0
        self.pastebuff = []
        self.system = system
        self.first = ''
        self.first_prompt = '##'

        self.grid()
        self.createWidgets()

    def createWidgets(self):
        font = tkfont.Font(family='Courier New', size=15)
        style = ttk.Style()
        style.configure('.', font=font)

        # Center frame 
        #self.center = tk.Frame(self, bd=2, relief=tk.SUNKEN)
        self.center = ttk.Frame(self)
        self.center.grid(row=0, sticky=EAST_WEST)
        #self.center.grid_rowconfigure(0, weight=1)
        #self.center.grid_columnconfigure(0, weight=1)

        self.console = ReadOnlyText(self.master, self.center, height = 25, width = 89, fg='#04fe7c',
                                    bg='#292929', font = ('Courier New', 15))
        self.console.grid(row=0, column=0, sticky=ALL_SIDES)
        self.console.bind('<Key>', self.keypress)
        self.console.bind('<Control_L>', self.control_key)
        self.console.bind('<Meta_L>', self.control_key)
        self.console.focus_set()

        self.debug = ReadOnlyText(self.master, self.center, height = 5, width = 89, font = ('Courier New', 13), relief=tk.SUNKEN)
        self.debug.grid(row=1, column=0, sticky=ALL_SIDES)

        self.bottom = ttk.Frame(self)
        self.bottom.grid(row=2, sticky=tk.W)
        self.ips_label = tk.Label(self.bottom, text='', font = font, relief=tk.SUNKEN, width = 11)
        self.ips_label.grid(row=0, column=0, sticky=tk.W)
        self.start_button = tk.Button(self.bottom, text='Start routine', command=self.start)
        self.start_button.grid(row=0, column=1, sticky=tk.W)
        self.paste_button = tk.Button(self.bottom, text='Paste', command=self.paste)
        self.paste_button.grid(row=0, column=2, sticky=tk.W)
    
    def start(self):
        if self.first_prompt != '# ':
            self.paste('unix\n')
            self.first = None       # don't show the "type unix" hint
            self.first_prompt = ''  # track the first prompt 
            self.debug.println("Start routine loads UNIX for you and configures terminal to allow lowercase letters.")
        else:
            self.paste('stty -lcase\n')

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

    def control_key(self, event):
        #print('Control:',event)
        pass

    def control_up_key(self, event):
        #print('Control Up:',event)
        pass
    
    def keypress(self, event):
        ch = event.char
        if len(ch)==1 and ord(ch)<256:
            #print('Key:', event)
            if ch == '\r': ch = '\n'
            if self.first != None:
                if ch == '\n':
                    if self.first != 'unix':
                        self.console.println("")
                        self.console.println("hint: type \"unix\" command to run Unix V6")
                    self.first = None
                else:
                    self.first += ch
            self.keybuff_lock.acquire()
            self._addchar(ord(event.char))
            self.keybuff_lock.release()

    def cleardebug(self):
        self.debug.clear()

    def clear(self):        # terminal
        # Clear terminal screen
        #var len = document.getElementById("terminal").firstChild.nodeValue.length;
        #document.getElementById("terminal").firstChild.deleteData(0, len);
        self.console.clear()

        self.TKS = 0
        self.TPS = 1<<7
        self.T = None

    def writedebug(self, msg):
        self.debug.print(msg)

    def write(self, msg):   # terminal
        # Add text to the terminal
        self.console.print(msg)
        if len(self.first_prompt)<2:
            if not self.first_prompt and msg == '#':
                self.first_prompt += msg
            elif self.first_prompt=='#' and msg == ' ':
                self.first_prompt += msg
                self.paste('stty -lcase\n')

    def _addchar(self, c):
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
        if a == 0o777560:
            return self.TKS
        elif a == 0o777562:
            return self._getchar()
        elif a == 0o777564:
            return self.TPS
        elif a == 0o777566:
            return 0
        self.system.panic("read from invalid address " + ostr(a,6))

    def conswrite16(self, a, v):
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
                self.write(chr(v & 0x7F))
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

    def show_ips(self, ips):
        self.ips_label.config(text='MIPS ={:-5.2f}'.format(ips/1000000))
    
