#!/usr/bin/env python3

# This is a translation of Julius Schmidt's PDP-11 emulator in JavaScript.
# You can run that one in your browser: http://pdp11.aiju.de
# (c) 2011, Julius Schmidt, JavaScript implementation, MIT License
# (c) 2019, Andriy Makukha, ported to Python 3, MIT License
# Version 6 Unix (in the disk image) is available under the four-clause BSD license.

import time
from threading import Timer
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
    def println(self, text):
        self.print(text + '\n')
    def print(self, text):
        #print("print = ", repr(text))
        if text == '\r': return
        self.config(state=tk.NORMAL)
        lines = float(self.index(tk.END))
        if lines >= self.MAX_LINES:
            self.delete(1.0, lines - self.MAX_LINES)
        self.insert(tk.END, text)
        self.config(state=tk.DISABLED)
        self.see(tk.END)
    def clear(self):
        self.config(state=tk.NORMAL)
        lines = float(self.index(tk.END))
        self.delete(1.0, lines)
        self.config(state=tk.DISABLED)
        self.see(tk.END)
        

class Terminal(ttk.Frame):
    def __init__(self, system):
        if tk.TclVersion < 8.6:
            print('WARNING: your Tcl version %s is too old', tkinter.TclVersion)
        super(Terminal, self).__init__(None)

        self.TKS = 0
        self.TPS = 0
        self.keybuf = 0
        self.system = system
        self.first = ''

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
        self.center.grid_rowconfigure(0, weight=1)
        self.center.grid_columnconfigure(0, weight=1)

        self.console = ReadOnlyText(self.master, self.center, height = 25, width = 89, fg='#04fe7c',
                                    bg='#292929', font = ('Courier New', 15))
        self.console.grid(row=0, column=0, sticky=ALL_SIDES)
        self.console.bind('<Key>', self.keypress)
        self.console.focus_set()

        self.debug = ReadOnlyText(self.master, self.center, height = 5, width = 89, font = ('Courier New', 13), relief=tk.SUNKEN)
        self.debug.grid(row=1, column=0, sticky=ALL_SIDES)

        self.ips_label = tk.Label(self, text='', font = font, relief=tk.SUNKEN, width = 11)
        self.ips_label.grid(row=2, sticky=tk.W)
    
    def keypress(self, event):
        ch = event.char
        if len(ch)==1 and ord(ch)<256:
            print("pressed", repr(ch))
            if ch == '\r': ch = '\n'
            if self.first != None:
                if ch == '\n':
                    if self.first != 'unix':
                        self.console.println("")
                        self.console.println("hint: type \"unix\" command to run Unix V6")
                    self.first = None
                else:
                    self.first += ch
            self._addchar(ord(event.char))

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
        #var ta = document.getElementById("terminal");
        #ta.firstChild.appendData(msg);
        #ta.scrollTop = ta.scrollHeight;
        self.console.print(msg)

    def _addchar(self, c):
        print ('ADDCHAR = %d' % c)
        self.TKS |= 0x80
        self.keybuf = c             # TODO: allow bigger buffer?
        if self.TKS & (1<<6):
            self.system.interrupt(Interrupt.TTYIN, 4)       # TODO: thread safety

    def _specialchar(self, c):
        # TODO: onkeyup="specialchar(event.which)"
        if c == 42:     # '*'
            self.keybuf = 4
        elif c == 19:   # 0x13
            self.keybuf = 0o34
        elif c == 46:   # '.'  // EOF?
            self.keybuf = 127
        else:
            return
        self.TKS |= 0x80
        if self.TKS & (1<<6):
            self.system.interrupt(Interrupt.TTYIN, 4)

    def _getchar(self):
        if self.TKS & 0x80:
            self.TKS &= 0xff7e
            return self.keybuf
        return 0

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
            #print('v = ', hex(v))
            if not (self.TPS & 0x80):
                return
            if v == 13:     # ignoring '\r'
                return
            else: 
                self.write(chr(v & 0x7F))
            self.TPS &= 0xff7f
            if self.TPS & (1<<6):
                #setTimeout("TPS |= 0x80; interrupt(INTTTYOUT, 4);", 1);
                T = Timer(0.001, self._tps_flag_interrupt)
                #self._tps_flag_interrupt()
            else:
                #setTimeout("TPS |= 0x80;", 1);
                T = Timer(0.001, self._tps_flag)
                #self._tps_flag()
            T.start()
        else:
            system.panic("write to invalid address " + ostr(a,6));

    def _tps_flag(self):
        self.TPS |= 0x80

    def _tps_flag_interrupt(self):
        self.TPS |= 0x80
        self.system.interrupt(Interrupt.TTYOUT, 4)

    def show_ips(self, ips):
        self.ips_label.config(text='MIPS ={:-5.2f}'.format(ips/1000000))
    
