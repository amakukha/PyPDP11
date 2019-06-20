#!/usr/bin/env python3

# This is a translation of Julius Schmidt's PDP-11 emulator in JavaScript.
# You can run that one in your browser: http://pdp11.aiju.de
# (c) 2011, Julius Schmidt, JavaScript implementation, MIT License
# (c) 2019, Andriy Makukha, ported to Python 3, MIT License
# Version 6 Unix (in the disk image) is available under the four-clause BSD license.

class Interrupt:

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

    def __init__(self, vec, pri):
        self.vec = vec
        self.pri = pri


