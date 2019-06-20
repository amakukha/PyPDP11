#!/usr/bin/env python3

# This is a translation of Julius Schmidt's PDP-11 emulator in JavaScript.
# You can run that one in your browser: http://pdp11.aiju.de
# (c) 2011, Julius Schmidt, JavaScript implementation, MIT License
# (c) 2019, Andriy Makukha, ported to Python 3, MIT License
# Version 6 Unix (in the disk image) is available under the four-clause BSD license.

import time
from threading import Timer
from interrupt import Interrupt

def ostr(d, n=6):
    return '{{:0{}o}}'.format(n).format(d)

class Terminal:
    def __init__(self, system):
        self.TKS = 0
        self.TPS = 0
        self.keybuf = 0
        self.system = system

        self.file = open('terminal.txt', 'w')
    
    def clear(self):        # terminal
        # Clear terminal screen
        #var len = document.getElementById("terminal").firstChild.nodeValue.length;
        #document.getElementById("terminal").firstChild.deleteData(0, len);
        # TODO
        self.TKS = 0
        self.TPS = 1<<7
        self.first = True
        self.T = None

    def write(self, msg):   # terminal
        # Add text to the terminal
        #var ta = document.getElementById("terminal");
        #ta.firstChild.appendData(msg);
        #ta.scrollTop = ta.scrollHeight;
        # TODO
        self.file.write(msg)
        self.file.flush()
        if self.first:
            print('Starting UNIX')
            self.T = Timer(1, self._unix)
            self.T.start()
            self.first = False

    def _addchar(self, c):
        # TODO: onkeypress="addchar(event.which)"
        print ('ADDCHAR = %d' % c)
        self.TKS |= 0x80
        self.keybuf = c             # TODO: allow bigger buffer
        if self.TKS & (1<<6):
            self.system.interrupt(Interrupt.TTYIN, 4)       # TODO: thread safety

    def _unix(self):
        self._addchar(ord('u'))
        time.sleep(1)
        self._addchar(ord('n'))
        time.sleep(1)
        self._addchar(ord('i'))
        time.sleep(1)
        self._addchar(ord('x'))
        time.sleep(1)
        self._addchar(ord('\r'))

    def _specialchar(self, c):
        # TODO: onkeyup="specialchar(event.which)"
        if c == 42:     # '*'
            self.keybuf = 4
        elif c == 19:   # 0x13
            self.keybuf = 0o34
        elif c == 46:   # '.'
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
            v &= 0xFF
            if not (self.TPS & 0x80):
                return
            if v == 13:     # TODO: why ignored?
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

    
