#!/usr/bin/env python3

# This code is based on Julius Schmidt's PDP-11 emulator for JavaScript.
# You can run that one in your browser: http://pdp11.aiju.de
# (c) 2011, Julius Schmidt, JavaScript/HTML implementation, MIT License
# (c) 2019, Andriy Makukha, ported to Python 3, MIT License
# Version 6 Unix (in the disk image) is available under the four-clause BSD license.

class Interrupt:

    MAX_PRIORITY = 7

    # Traps
    BUS     = 0o004
    INVAL   = 0o010
    DEBUG   = 0o014
    IOT     = 0o020
    TTYIN   = 0o060
    TTYOUT  = 0o064
    FAULT   = 0o250
    CLOCK   = 0o100
    RK      = 0o220

    # PyPDP11: these event should be called with interrupt priority 0 (to be executed last)
    ExtractImage =  0o410
    LoadImage    =  0o420
    Synchronize  =  0o440
    Reset        = 0o1400

    def __init__(self, vec, pri):
        self.vec = vec
        self.pri = pri

    def __lt__(self, other):
        '''Higher priority interrupts must go to the beginning of PriorityQueue'''
        if self.pri > other.pri:
            return True
        if self.pri == other.pri and self.vec < other.vec:
            return True
        return False


