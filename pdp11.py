#!/usr/bin/env python3

# This code is based on Julius Schmidt's PDP-11 emulator for JavaScript.
# You can run that one in your browser: http://pdp11.aiju.de
# (c) 2011, Julius Schmidt, JavaScript/HTML implementation, MIT License
# (c) 2019, Andriy Makukha, ported to Python 3, MIT License
# Version 6 Unix (in the disk image) is available under the four-clause BSD license.
# This implementation has two main threads: GUI and CPU (this file). They exchange `interrupts`
# through Python's PriorityQueue. Additional thread is added for the clock interrupt.

import time, array, threading, queue

from rk05 import RK05
from cons import Terminal, ostr
from interrupt import Interrupt
from disasm import DISASM_TABLE

INT = Interrupt     # shorthand for Interrupt

class Trap(Exception):
    def __init__(self, num, *args):
        Exception.__init__(self, *args)
        self.num = num

class Page:
    def __init__(self, par, pdr):
        self.par = par
        self.pdr = pdr
        self.addr = par & 0o7777
        self.len = (pdr >> 8) & 0x7F
        self.read = (pdr & 2) == 2
        self.write = (pdr & 6) == 6
        self.ed = (pdr & 8) == 8

class PDP11:

    FLAGN = 8
    FLAGZ = 4
    FLAGV = 2
    FLAGC = 1

    BOOTROM = [
        0o042113,                        ## "KD" 
        0o012706, 0o2000,                ## MOV #boot_start, SP 
        0o012700, 0o000000,              ## MOV #unit, R0        ; unit number 
        0o010003,                        ## MOV R0, R3 
        0o000303,                        ## SWAB R3 
        0o006303,                        ## ASL R3 
        0o006303,                        ## ASL R3 
        0o006303,                        ## ASL R3 
        0o006303,                        ## ASL R3 
        0o006303,                        ## ASL R3 
        0o012701, 0o177412,              ## MOV #RKDA, R1        ; csr 
        0o010311,                        ## MOV R3, (R1)         ; load da 
        0o005041,                        ## CLR -(R1)            ; clear ba 
        0o012741, 0o177000,              ## MOV #-256.*2, -(R1)  ; load wc 
        0o012741, 0o000005,              ## MOV #READ+GO, -(R1)  ; read & go 
        0o005002,                        ## CLR R2 
        0o005003,                        ## CLR R3 
        0o012704, 0o2020,                ## MOV #START+20, R4 
        0o005005,                        ## CLR R5 
        0o105711,                        ## TSTB (R1) 
        0o100376,                        ## BPL .-2 
        0o105011,                        ## CLRB (R1) 
        0o005007                         ## CLR PC 
    ]

    RS = ["R0", "R1", "R2", "R3", "R4", "R5", "SP", "PC"]

    def __init__(self):
        # TODO: why are these not in reset()
        self.prdebug = False
        self.SR2 = 0
        self.interrupts = queue.PriorityQueue()
        self.last_interrupt_priority = INT.MAX_PRIORITY
        self.lastTime = time.time()

        # Terminal
        self.terminal = Terminal(self)
        self.terminal.master.title("PDP-11 emulator @ Python")
        self.place_window(self.terminal.master)

        # Magnetic disk drive
        self.rk = RK05(self)

        self.reset()
    
    def place_window(self, master):
        try:
            master.update_idletasks()
        except:
            return
        sw = master.winfo_screenwidth()
        sh = master.winfo_screenheight()
        w, h = map(int, master.geometry().split('+')[0].split('x'))
        x = max(int((sw-w)/3), 0)
        y = max(int((sh-h)/2), 0)
        master.geometry('{}x{}+{}+{}'.format(w, h, x, y))

    def reset(self):
        self.R = [0, 0, 0, 0, 0, 0, 0, 0]       # registers
        self.KSP = 0        # kernel mode stack pointer
        self.USP = 0        # user mode stack pointer
        self.PS = 0         # processor status
        self.curPC = 0      # address of current instruction
        self.instr = 0      # current instruction
        self.memory = array.array('H', bytearray(256*1024*[0]))     # 128K of 16-bit unsigned values
        self.ips = 0
        self.SR0 = 0
        self.curuser = False
        self.prevuser = False
        self.LKS = 0x80     # Line Frequency Clock
        self.step_cnt = 0

        # from reset():
        for i in range(len(PDP11.BOOTROM)):
            self.memory[0o1000+i] = PDP11.BOOTROM[i]
        self.pages = [Page(0, 0) for _ in range(16)]
        self.R[7] = 0o2002

        self.cleardebug()
        self.terminal.clear()
        self.rk.reset()

        self.running = threading.Event()
        self.running.set()


    @staticmethod
    def _xor(a, b):
        return (a or b) and not (a and b)


    def switchmode(self, newmode):
        self.prevuser = self.curuser
        self.curuser = newmode
        if self.prevuser:
            self.USP = self.R[6]
        else:
            self.KSP = self.R[6]
        if self.curuser:
            self.R[6] = self.USP
        else:
            self.R[6] = self.KSP
        self.PS &= 0o007777
        if self.curuser:
            self.PS |= (1<<15) | (1<<14)
        if self.prevuser:
            self.PS |= (1<<13) | (1<<12)


    def physread16(self, addr):
        if addr & 1:
            raise(Trap(INT.BUS, 'read from odd address ' + ostr(addr,6)))
        if addr < 0o760000:
            return self.memory[addr>>1]
        if addr == 0o777546:
            return self.LKS
        if addr == 0o777570:         # what does this do? 0o173030 = 63000
            return 0o173030
        if addr == 0o777572:
            return self.SR0
        if addr == 0o777576:
            return self.SR2
        if addr == 0o777776:
            return self.PS
        if (addr & 0o777770) == 0o777560: 
            return self.terminal.consread16(addr)
        if (addr & 0o777760) == 0o777400:
            return self.rk.read16(addr)
        if (addr & 0o777600) == 0o772200 or (addr & 0o777600) == 0o777600:
            return self.mmuread16(addr)
        if addr == 0o776000:
            self.panic('lolwut')
        raise(Trap(INT.BUS, 'read from invalid address ' + ostr(addr,6)))


    def physread8(self, addr):
        val = self.physread16(addr & ~1)
        if addr & 1:
            return val >> 8
        return val & 0xFF

    def physwrite8(self, a, v):
        if a < 0o760000:
            if a & 1:
                self.memory[a>>1] &= 0xFF
                self.memory[a>>1] |= (v & 0xFF) << 8
            else:
                self.memory[a>>1] &= 0xFF00
                self.memory[a>>1] |= v & 0xFF
        else:
            if a & 1:
                self.physwrite16(a&~1, (self.physread16(a) & 0xFF) | ((v & 0xFF) << 8))
            else:
                self.physwrite16(a&~1, (self.physread16(a) & 0xFF00) | (v & 0xFF))

    def physwrite16(self, a, v):
        if a % 1:
            raise(Trap(INT.BUS, "write to odd address " + ostr(a,6)))
        if a < 0o760000:
            try:
                self.memory[a>>1] = v
            except OverflowError as e:      # dirty fix of a problem
                if v < 0:
                    self.writedebug("warning: negative value @ physwrite16\n")
                    self.memory[a>>1] = v & 0xFFFF
                elif v > 0xFFFF:
                    self.writedebug("warning: short overflow @ physwrite16\n")
                    self.memory[a>>1] = v & 0xFFFF
                else:
                    raise e
        elif a == 0o777776:
            bits = (v >> 14) & 3
            if bits == 0:
                self.switchmode(False)
            elif bits == 3:
                self.switchmode(True)
            else:
                self.panic("invalid mode")
            bits = (v >> 12) & 3
            if bits == 0:
                self.prevuser = False
            elif bits == 3:
                self.prevuser = True
            else:
                self.panic("invalid mode")
            self.PS = v
        elif a == 0o777546:
            self.LKS = v
        elif a == 0o777572:
            self.SR0 = v
        elif (a & 0o777770) == 0o777560:
            self.terminal.conswrite16(a, v)
        elif (a & 0o777700) == 0o777400:
            self.rk.write16(a,v)
        elif (a & 0o777600) == 0o772200 or (a & 0o777600) == 0o777600:
            self.mmuwrite16(a,v)
        else:
            raise(Trap(INT.BUS, "write to invalid address " + ostr(a,6)))


    def decode(self, a, w, m):
        #var p, user, block, disp
        if not (self.SR0 & 1):
            if a >= 0o170000:
                a += 0o600000
            return a
        user = 8 if m else 0
        p = self.pages[(a >> 13) + user]
        if w and not p.write:
            self.SR0 = (1<<13) | 1
            self.SR0 |= (a >> 12) & ~1
            if user:
                self.SR0 |= (1<<5) | (1<<6)
            self.SR2 = self.curPC
            raise(Trap(INT.FAULT, "write to read-only page " + ostr(a,6)))
        if not p.read:
            self.SR0 = (1<<15) | 1
            self.SR0 |= (a >> 12) & ~1
            if user:
                self.SR0 |= (1<<5)|(1<<6)
            self.SR2 = self.curPC
            raise(Trap(INT.FAULT, "read from no-access page " + ostr(a,6)))
        block = (a >> 6) & 0o177
        disp = a & 0o77
        if (p.ed and (block < p.len)) or (not p.ed and (block > p.len)):
                self.SR0 = (1<<14) | 1
                self.SR0 |= (a >> 12) & ~1
                if user:
                    self.SR0 |= (1<<5)|(1<<6)
                self.SR2 = self.curPC
                raise(Trap(INT.FAULT, "page length exceeded, address " + ostr(a,6) + " (block " + \
                      ostr(block,3) + ") is beyond length " + ostr(p.len,3)))
        if w:
            p.pdr |= 1<<6
        return ((block + p.addr) << 6) + disp


    def mmuread16(self, a):
        i = (a & 0o17)>>1
        if (a >= 0o772300) and (a < 0o772320):
                return self.pages[i].pdr
        if (a >= 0o772340) and (a < 0o772360):
                return self.pages[i].par
        if (a >= 0o777600) and (a < 0o777620):
                return self.pages[i+8].pdr
        if (a >= 0o777640) and (a < 0o777660):
                return self.pages[i+8].par
        raise(Trap(INT.BUS, "invalid read from " + ostr(a,6)))


    def mmuwrite16(self, a, v):
        i = (a & 0o17)>>1
        if (a >= 0o772300) and (a < 0o772320):
            self.pages[i] = Page(self.pages[i].par, v)
        elif (a >= 0o772340) and (a < 0o772360):
            self.pages[i] = Page(v, self.pages[i].pdr)
        elif (a >= 0o777600) and (a < 0o777620):
            self.pages[i+8] = Page(self.pages[i+8].par, v)
        elif (a >= 0o777640) and (a < 0o777660):
            self.pages[i+8] = Page(v, self.pages[i+8].pdr)
        else:
            raise(Trap(INT.BUS, "write to invalid address " + ostr(a,6)))

    def read8(self, a):
        return self.physread8(self.decode(a, False, self.curuser))

    def read16(self, a):
        return self.physread16(self.decode(a, False, self.curuser))

    def write8(self, a, v):
        return self.physwrite8(self.decode(a, True, self.curuser), v)

    def write16(self, a, v):
        return self.physwrite16(self.decode(a, True, self.curuser), v)

    def fetch16(self):
        val = self.read16(self.R[7])
        self.R[7] += 2
        return val

    def push(self, v):
        self.R[6] -= 2
        self.write16(self.R[6], v)

    def pop(self):
        val = self.read16(self.R[6])
        self.R[6] += 2
        return val

    def disasmaddr(self, m, a):
        if (m & 7) == 7:
            if m ==  0o27:
                a[0] += 2
                return "$" + oct(self.memory[a[0]>>1])[2:]
            elif m == 0o37:
                a[0] += 2
                return "*" + oct(self.memory[a[0]>>1])[2:]
            elif m == 0o67:
                a[0] += 2
                return "*" + oct((a[0] + 2 + self.memory[a[0]>>1]) & 0xFFFF)[2:]
            elif m == 0o77:
                a[0] += 2
                return "**" + oct((a[0] + 2 + self.memory[a[0]>>1]) & 0xFFFF)[2:]
        r = PDP11.RS[m & 7]
        bits = m & 0o70
        if bits == 0o00:
            return r
        elif bits == 0o10:
            return "(" + r + ")"
        elif bits == 0o20:
            return "(" + r + ")+"
        elif bits == 0o30:
            return "*(" + r + ")+"
        elif bits == 0o40:
            return "-(" + r + ")"
        elif bits == 0o50:
            return "*-(" + r + ")"
        elif bits == 0o60:
            a[0]+=2
            return oct(self.memory[a[0]>>1])[2:] + "(" + r + ")"
        elif bits == 0o70:
            a[0]+=2
            return "*" + oct(self.memory[a[0]>>1])[2:] + "(" + r + ")"

    def disasm(self, a):
        #var i, ins, l, msg, s, d;
        ins = self.memory[a>>1]         # instruction
        msg = None
        for l in DISASM_TABLE:
            if (ins & l[0]) == l[1]:
                msg = l[2]
                break
        if not msg:
            return "???"
        if l[4] and ins & 0o100000:
            msg += "B"
        s = (ins & 0o7700) >> 6
        d = ins & 0o77
        o = ins & 0o377
        aa = [a]

        if l[3] == "SD" or l[3] == "D":
            if l[3] == "SD":
                msg += " " + self.disasmaddr(s, aa) + ","
            msg += " " + self.disasmaddr(d, aa)
        elif l[3] == "D":
            msg += " " + self.disasmaddr(d, aa)
        elif l[3] == "RO" or l[3] == "O":
            if l[3] == "RO":
                msg += " " + PDP11.RS[(ins & 0o700) >> 6] + ","; o &= 0o77
            if o & 0x80:
                msg += " -" + oct(2*((0xFF ^ o) + 1))[2:]
            else:
                msg += " +" + oct(2*o)[2:]
        elif l[3] == "RD":
            msg += " " + PDP11.RS[(ins & 0o700) >> 6] + ", " + self.disasmaddr(d, aa)
        elif l[3] == "R":
            msg += " " + PDP11.RS[ins & 7]
        elif l[3] == "R3":
            msg += " " + PDP11.RS[(ins & 0o700) >> 6]
        return msg

    def cleardebug(self):
        self.terminal.cleardebug()

    def writedebug(self, msg):
        self.terminal.writedebug(msg)

    def printstate(self):
        # Display registers
        self.writedebug(str(self.step_cnt)+'\n')
        self.writedebug(
                "R0 " + ostr(self.R[0]) + "  " + \
                "R1 " + ostr(self.R[1]) + "  " + \
                "R2 " + ostr(self.R[2]) + "  " + \
                "R3 " + ostr(self.R[3]) + "  " + \
                "R4 " + ostr(self.R[4]) + "  " + \
                "R5 " + ostr(self.R[5]) + "  " + \
                "R6 " + ostr(self.R[6]) + "  " + \
                "R7 " + ostr(self.R[7]) + "\n"
        )
        self.writedebug( "[" + \
            ("u" if self.prevuser else "k") + \
            ("U" if self.curuser else "K") + \
            ("N" if (self.PS & PDP11.FLAGN) else " ") + \
            ("Z" if (self.PS & PDP11.FLAGZ) else " ") + \
            ("V" if (self.PS & PDP11.FLAGV) else " ") + \
            ("C" if (self.PS & PDP11.FLAGC) else " ") + \
            "]  instr " + ostr(self.curPC) + ": " + ostr(self.instr) + "   "
        )
        try:
            decoded = self.decode(self.curPC, False, self.curuser)
            self.writedebug(self.disasm(decoded) + "\n")
        except Exception:
            pass

    def panic(self, msg):
        self.writedebug('PANIC: ' + msg + '\n')
        self.printstate()
        self.stop()
        raise Exception(msg)

    def interrupt(self, vec, pri):
        # This is called by CPU, GUI and clock threads
        if vec & 1:
            self.panic("Thou darst calling interrupt() with an odd vector number?")
        self.interrupts.put(Interrupt(vec, pri))
        self.running.set()

    def clock(self):
        while not self.clock_stop.is_set():           
            time.sleep(0.02)

            # Clock interrupt
            self.LKS |= 0x80                    # bit 7: set to 1 every 20 ms
            if self.LKS & 0x40:                 # bit 6: when set, an interrupt will occur
                self.interrupt(INT.CLOCK, 6)

        print('- clock stopped')

    def handleinterrupt(self, vec):
        try:
            prev = self.PS
            self.switchmode(False)
            self.push(prev)
            self.push(self.R[7])
        except Trap as e:
            self.trapat(e.num, str(e))
        self.R[7] = self.memory[vec>>1]
        self.PS = self.memory[(vec>>1)+1]
        if self.prevuser:
            self.PS |= (1<<13) | (1<<12)

    def trapat(self, vec, msg):
        #var prev;
        if vec & 1:
            self.panic("Thou darst calling trapat() with an odd vector number?")
        self.writedebug("trap " + ostr(vec) + " occured: " + msg + "\n")
        self.printstate()
        try:
            prev = self.PS
            self.switchmode(False)
            self.push(prev)
            self.push(self.R[7])
        except Exception as e:
            if 'num' in e.__dir__:
                self.writedebug("red stack trap!\n")
                self.memory[0] = self.R[7]
                self.memory[1] = prev
                vec = 4
            else:
                raise(e)
        self.R[7] = self.memory[vec>>1]
        self.PS = self.memory[(vec>>1)+1]
        if self.prevuser:
            self.PS |= (1<<13) | (1<<12)
        self.running.set()


    def aget(self, v, l):
        #var addr
        if (v & 7) >= 6 or (v & 0o10):
            l = 2
        if (v & 0o70) == 0o00:
            return -(v + 1)
        bits = v & 0o60
        if bits == 0o00:
            v &= 7
            addr = self.R[v & 7]
        elif bits == 0o20:
            addr = self.R[v & 7]
            self.R[v & 7] += l
        elif bits == 0o40:
            self.R[v & 7] -= l
            addr = self.R[v & 7]
        elif bits == 0o60:
            addr = self.fetch16()
            addr += self.R[v & 7]
        addr &= 0xFFFF
        if v & 0o10:
            addr = self.read16(addr)
        return addr


    def memread(self, a, l):
        if a < 0:
            if l == 2:
                return self.R[-(a + 1)]
            else:
                return self.R[-(a + 1)] & 0xFF
        if l == 2:
            return self.read16(a)
        return self.read8(a)


    def memwrite(self, a, l, v):
        if a < 0:
            if l == 2:
                self.R[-(a + 1)] = v
            else:
                self.R[-(a + 1)] &= 0xFF00
                self.R[-(a + 1)] |= v
        elif l == 2:
            self.write16(a, v)
        else:
            self.write8(a, v)


    def branch(self, o):
        if o & 0x80:
            o = -(((~o)+1)&0xFF)
        o <<= 1
        self.R[7] += o


    def step(self):
        #var val, val1, val2, ia, da, sa, d, s, l, r, o, max, maxp, msb;
        self.ips += 1
        self.step_cnt += 1
        self.curPC = self.R[7]
        ia = self.decode(self.R[7], False, self.curuser)            # instruction address
        self.R[7] += 2
        self.instr = self.physread16(ia)
        d = self.instr & 0o77
        s = (self.instr & 0o7700) >> 6
        l = 2 - (self.instr >> 15)
        o = self.instr & 0xFF
        if l == 2:
            max = 0xFFFF
            maxp = 0x7FFF
            msb = 0x8000
        else:
            max = 0xFF
            maxp = 0x7F
            msb = 0x80

        # MOV / CMP / BIT / BIC / BIS
        bits = self.instr & 0o070000
        if bits == 0o010000: # MOV
            sa = self.aget(s, l); val = self.memread(sa, l)
            da = self.aget(d, l)
            self.PS &= 0xFFF1
            if val & msb:
                self.PS |= PDP11.FLAGN
            if val == 0:
                self.PS |= PDP11.FLAGZ
            if da < 0 and l == 1:
                l = 2
                if val & msb:
                    val |= 0xFF00
            self.memwrite(da, l, val)
            return
        elif bits == 0o020000: # CMP
            sa = self.aget(s, l); val1 = self.memread(sa, l)
            da = self.aget(d, l); val2 = self.memread(da, l)
            val = (val1 - val2) & max
            self.PS &= 0xFFF0
            if val == 0:
                self.PS |= PDP11.FLAGZ
            if val & msb:
                self.PS |= PDP11.FLAGN
            if ((val1 ^ val2) & msb) and not ((val2 ^ val) & msb):
                self.PS |= PDP11.FLAGV
            if val1 < val2:
                self.PS |= PDP11.FLAGC
            return
        elif bits == 0o030000: # BIT
            sa = self.aget(s, l); val1 = self.memread(sa, l)
            da = self.aget(d, l); val2 = self.memread(da, l)
            val = val1 & val2
            self.PS &= 0xFFF1
            if val == 0:
                self.PS |= PDP11.FLAGZ
            if val & msb:
                self.PS |= PDP11.FLAGN
            return
        elif bits == 0o040000: # BIC
            sa = self.aget(s, l); val1 = self.memread(sa, l)
            da = self.aget(d, l); val2 = self.memread(da, l)
            val = (max ^ val1) & val2
            self.PS &= 0xFFF1
            if val == 0:
                self.PS |= PDP11.FLAGZ
            if val & msb:
                self.PS |= PDP11.FLAGN
            self.memwrite(da, l, val)
            return
        elif bits == 0o050000: # BIS
            sa = self.aget(s, l); val1 = self.memread(sa, l)
            da = self.aget(d, l); val2 = self.memread(da, l)
            val = val1 | val2
            self.PS &= 0xFFF1
            if val == 0:
                self.PS |= PDP11.FLAGZ
            if val & msb:
                self.PS |= PDP11.FLAGN
            self.memwrite(da, l, val)
            return

        # ADD / SUB
        bits = self.instr & 0o170000
        if bits == 0o060000: # ADD
            sa = self.aget(s, 2); val1 = self.memread(sa, 2)
            da = self.aget(d, 2); val2 = self.memread(da, 2)
            val = (val1 + val2) & 0xFFFF
            self.PS &= 0xFFF0
            if val == 0:
                self.PS |= PDP11.FLAGZ
            if val & 0x8000:
                self.PS |= PDP11.FLAGN
            if not ((val1 ^ val2) & 0x8000) and ((val2 ^ val) & 0x8000):
                self.PS |= PDP11.FLAGV
            if val1 + val2 >= 0xFFFF:
                self.PS |= PDP11.FLAGC
            self.memwrite(da, 2, val)
            return
        elif bits == 0o160000: # SUB
            sa = self.aget(s, 2); val1 = self.memread(sa, 2)
            da = self.aget(d, 2); val2 = self.memread(da, 2)
            val = (val2 - val1) & 0xFFFF
            self.PS &= 0xFFF0
            if val == 0:
                self.PS |= PDP11.FLAGZ
            if val & 0x8000:
                self.PS |= PDP11.FLAGN
            if ((val1 ^ val2) & 0x8000) and not ((val2 ^ val) & 0x8000):
                self.PS |= PDP11.FLAGV
            if val1 > val2:
                self.PS |= PDP11.FLAGC
            self.memwrite(da, 2, val)
            return

        # JSR / MUL / DIV / ASH / ASHC / XOR / SOB
        bits = self.instr & 0o177000
        if bits == 0o004000: # JSR
            val = self.aget(d, l)
            if val >= 0:
                self.push(self.R[s & 7])
                self.R[s & 7] = self.R[7]
                self.R[7] = val
                return
        elif bits == 0o070000: # MUL
            val1 = self.R[s & 7]
            if val1 & 0x8000:
                val1 = -((0xFFFF^val1)+1)
            da = self.aget(d, l); val2 = self.memread(da, 2)
            if val2 & 0x8000:
                val2 = -((0xFFFF^val2)+1)
            val = val1 * val2
            self.R[s & 7] = (val & 0xFFFF0000) >> 16
            self.R[(s & 7)|1] = val & 0xFFFF
            self.PS &= 0xFFF0
            if val & 0x80000000:
                self.PS |= PDP11.FLAGN
            if (val & 0xFFFFFFFF) == 0:
                self.PS |= PDP11.FLAGZ
            if val < (1<<15) or val >= ((1<<15)-1):
                self.PS |= PDP11.FLAGC
            return
        elif bits == 0o071000: # DIV
            val1 = (self.R[s & 7] << 16) | self.R[(s & 7) | 1]
            da = self.aget(d, l); val2 = self.memread(da, 2)
            self.PS &= 0xFFF0
            if val2 == 0:
                self.PS |= PDP11.FLAGC
                return
            if (val1 / val2) >= 0x10000:
                self.PS |= PDP11.FLAGV
                return
            self.R[s & 7] = (val1 // val2) & 0xFFFF
            self.R[(s & 7) | 1] = (val1 % val2) & 0xFFFF
            if self.R[s & 7] == 0:
                self.PS |= PDP11.FLAGZ
            if self.R[s & 7] & 0o100000:
                self.PS |= PDP11.FLAGN
            if val1 == 0:
                self.PS |= PDP11.FLAGV
            return
        elif bits == 0o072000: # ASH
            val1 = self.R[s & 7]
            da = self.aget(d, 2); val2 = self.memread(da, 2) & 0o77
            self.PS &= 0xFFF0
            if val2 & 0o40:
                val2 = (0o77 ^ val2) + 1
                if val1 & 0o100000:
                    val = 0xFFFF ^ (0xFFFF >> val2)
                    val |= val1 >> val2
                else:
                    val = val1 >> val2
                if val1 & (1 << (val2 - 1)):
                    self.PS |= PDP11.FLAGC
            else:
                val = (val1 << val2) & 0xFFFF
                if val1 & (1 << (16 - val2)):
                    self.PS |= PDP11.FLAGC
            self.R[s & 7] = val
            if val == 0:
                self.PS |= PDP11.FLAGZ
            if val & 0o100000:
                self.PS |= PDP11.FLAGN
            if self._xor(val & 0o100000, val1 & 0o100000):
                self.PS |= PDP11.FLAGV
            return
        elif bits == 0o073000: # ASHC
            val1 = (self.R[s & 7] << 16) | self.R[(s & 7) | 1]
            da = self.aget(d, 2); val2 = self.memread(da, 2) & 0o77
            self.PS &= 0xFFF0
            if val2 & 0o40:
                val2 = (0o77 ^ val2) + 1
                if val1 & 0x80000000:
                    val = 0xFFFFFFFF ^ (0xFFFFFFFF >> val2)
                    val |= val1 >> val2
                else:
                    val = val1 >> val2
                if val1 & (1 << (val2 - 1)):
                    self.PS |= PDP11.FLAGC
            else:
                val = (val1 << val2) & 0xFFFFFFFF
                if val1 & (1 << (32 - val2)):
                    self.PS |= PDP11.FLAGC
            self.R[s & 7] = (val >> 16) & 0xFFFF
            self.R[(s & 7)|1] = val & 0xFFFF
            if val == 0:
                self.PS |= PDP11.FLAGZ
            if val & 0x80000000:
                self.PS |= PDP11.FLAGN
            if self._xor(val & 0x80000000, val1 & 0x80000000):
                self.PS |= PDP11.FLAGV
            return
        elif bits == 0o074000: # XOR
            val1 = self.R[s & 7]
            da = self.aget(d, 2); val2 = self.memread(da, 2)
            val = val1 ^ val2
            self.PS &= 0xFFF1
            if val == 0:
                self.PS |= PDP11.FLAGZ
            if val & 0x8000:
                self.PS |= PDP11.FLAGZ
            self.memwrite(da, 2, val)
            return
        elif bits == 0o077000: # SOB
            self.R[s & 7] -= 1
            if self.R[s & 7]:
                o &= 0o77
                o <<= 1
                self.R[7] -= o
            return

        # CLR / COM / INC / DEC / NEG / ADC / SBC / TST / ROL / ROR / ASL / AST / SXT
        bits = self.instr & 0o077700
        if bits == 0o005000: # CLR
            self.PS &= 0xFFF0
            self.PS |= PDP11.FLAGZ
            da = self.aget(d, l)
            self.memwrite(da, l, 0)
            return
        elif bits == 0o005100: # COM
            da = self.aget(d, l)
            val = self.memread(da, l) ^ max
            self.PS &= 0xFFF0; self.PS |= PDP11.FLAGC
            if val & msb:
                self.PS |= PDP11.FLAGN
            if val == 0:
                self.PS |= PDP11.FLAGZ
            self.memwrite(da, l, val)
            return
        elif bits == 0o005200: # INC
            da = self.aget(d, l)
            val = (self.memread(da, l) + 1) & max
            self.PS &= 0xFFF1
            if val & msb:
                self.PS |= PDP11.FLAGN | PDP11.FLAGV
            if val == 0:
                self.PS |= PDP11.FLAGZ
            self.memwrite(da, l, val)
            return
        elif bits == 0o005300: # DEC
            da = self.aget(d, l)
            val = (self.memread(da, l) - 1) & max
            self.PS &= 0xFFF1
            if val & msb:
                self.PS |= PDP11.FLAGN
            if val == maxp:
                self.PS |= PDP11.FLAGV
            if val == 0:
                self.PS |= PDP11.FLAGZ
            self.memwrite(da, l, val)
            return
        elif bits == 0o005400: # NEG
            da = self.aget(d, l)
            val = (-self.memread(da, l)) & max
            self.PS &= 0xFFF0
            if val & msb:
                self.PS |= PDP11.FLAGN
            if val == 0:
                self.PS |= PDP11.FLAGZ
            else:
                self.PS |= PDP11.FLAGC
            if val == 0x8000:
                self.PS |= PDP11.FLAGV
            self.memwrite(da, l, val)
            return
        elif bits == 0o005500: # ADC
            da = self.aget(d, l)
            val = self.memread(da, l)
            if self.PS & PDP11.FLAGC:
                self.PS &= 0xFFF0
                if (val + 1) & msb:
                    self.PS |= PDP11.FLAGN
                if val == max:
                    self.PS |= PDP11.FLAGZ
                if val == 0o077777:
                    self.PS |= PDP11.FLAGV
                if val == 0o177777:
                    self.PS |= PDP11.FLAGC
                self.memwrite(da, l, (val+1) & max)
            else:
                self.PS &= 0xFFF0
                if val & msb:
                    self.PS |= PDP11.FLAGN
                if val == 0:
                    self.PS |= PDP11.FLAGZ
            return
        elif bits == 0o005600: # SBC
            da = self.aget(d, l)
            val = self.memread(da, l)
            if self.PS & PDP11.FLAGC:
                self.PS &= 0xFFF0
                if (val - 1) & msb:
                    self.PS |= PDP11.FLAGN
                if val == 1:
                    self.PS |= PDP11.FLAGZ
                if val:
                    self.PS |= PDP11.FLAGC
                if val == 0o100000:
                    self.PS |= PDP11.FLAGV
                self.memwrite(da, l, (val-1) & max)
            else:
                self.PS &= 0xFFF0
                if val & msb:
                    self.PS |= PDP11.FLAGN
                if val == 0:
                    self.PS |= PDP11.FLAGZ
                if val == 0o100000:
                    self.PS |= PDP11.FLAGV
                self.PS |= PDP11.FLAGC
            return
        elif bits == 0o005700: # TST
            da = self.aget(d, l)
            val = self.memread(da, l)
            self.PS &= 0xFFF0
            if val & msb:
                self.PS |= PDP11.FLAGN
            if val == 0:
                self.PS |= PDP11.FLAGZ
            return
        elif bits == 0o006000: # ROR
            da = self.aget(d, l)
            val = self.memread(da, l)
            if self.PS & PDP11.FLAGC:
                val |= max+1
            self.PS &= 0xFFF0
            if val & 1:
                self.PS |= PDP11.FLAGC
            if val & (max+1):
                self.PS |= PDP11.FLAGN
            if not (val & max):
                self.PS |= PDP11.FLAGZ
            if self._xor(val & 1, val & (max+1)):
                self.PS |= PDP11.FLAGV
            val >>= 1
            self.memwrite(da, l, val)
            return
        elif bits == 0o006100: # ROL
            da = self.aget(d, l)
            val = self.memread(da, l) << 1
            if self.PS & PDP11.FLAGC:
                val |= 1
            self.PS &= 0xFFF0
            if val & (max+1):
                self.PS |= PDP11.FLAGC
            if val & msb:
                self.PS |= PDP11.FLAGN
            if not (val & max):
                self.PS |= PDP11.FLAGZ
            if (val ^ (val >> 1)) & msb:
                self.PS |= PDP11.FLAGV
            val &= max
            self.memwrite(da, l, val)
            return
        elif bits == 0o006200: # ASR
            da = self.aget(d, l)
            val = self.memread(da, l)
            self.PS &= 0xFFF0
            if val & 1:
                self.PS |= PDP11.FLAGC
            if val & msb:
                self.PS |= PDP11.FLAGN
            if self._xor(val & msb, val & 1):
                self.PS |= PDP11.FLAGV
            val = (val & msb) | (val >> 1)
            if val == 0:
                self.PS |= PDP11.FLAGZ
            self.memwrite(da, l, val)
            return
        elif bits == 0o006300: # ASL
            da = self.aget(d, l)
            val = self.memread(da, l)
            self.PS &= 0xFFF0
            if val & msb:
                self.PS |= PDP11.FLAGC
            if val & (msb >> 1):
                self.PS |= PDP11.FLAGN
            if (val ^ (val << 1)) & msb:
                self.PS |= PDP11.FLAGV
            val = (val << 1) & max
            if val == 0:
                self.PS |= PDP11.FLAGZ
            self.memwrite(da, l, val)
            return
        elif bits == 0o006700: # SXT
            da = self.aget(d, l)
            if self.PS & PDP11.FLAGN:
                self.memwrite(da, l, max)
            else:
                self.PS |= PDP11.FLAGZ
                self.memwrite(da, l, 0)
            return

        # JMP / SWAB / MARK / MFPI / MTPI
        bits = self.instr & 0o177700
        if bits == 0o000100: # JMP
            val = self.aget(d, 2)
            if val >= 0:
                self.R[7] = val
                return
        elif bits == 0o000300: # SWAB
            da = self.aget(d, l)
            val = self.memread(da, l)
            val = ((val >> 8) | (val << 8)) & 0xFFFF
            self.PS &= 0xFFF0
            if (val & 0xFF) == 0:
                self.PS |= PDP11.FLAGZ
            if val & 0x80:
                self.PS |= PDP11.FLAGN
            self.memwrite(da, l, val)
            return
        elif bits == 0o006400: # MARK
            self.R[6] = self.R[7] + (self.instr & 0o77) << 1
            self.R[7] = self.R[5]
            self.R[5] = self.pop()
            # TODO: no return here?
        elif bits == 0o006500: # MFPI
            da = self.aget(d, 2)
            if da == -7:
                val = self.R[6] if (self.curuser == self.prevuser) else (self.USP if self.prevuser else self.KSP)
            elif da < 0:
                self.panic("invalid MFPI instruction")
            else:
                val = self.physread16(self.decode(da, False, self.prevuser))
            self.push(val)
            self.PS &= 0xFFF0; self.PS |= PDP11.FLAGC
            if val == 0:
                self.PS |= PDP11.FLAGZ
            if val & 0x8000:
                self.PS |= PDP11.FLAGN
            return
        elif bits == 0o006600: # MTPI
            da = self.aget(d, 2)
            val = self.pop()
            if da == -7:
                if self.curuser == self.prevuser:
                    self.R[6] = val
                elif self.prevuser:
                    self.USP = val
                else:
                    self.KSP = val
            elif da < 0:
                self.panic("invalid MTPI instrution")
            else:
                sa = self.decode(da, True, self.prevuser)
                self.physwrite16(sa, val)
            self.PS &= 0xFFF0; self.PS |= PDP11.FLAGC
            if val == 0:
                self.PS |= PDP11.FLAGZ
            if val & 0x8000:
                self.PS |= PDP11.FLAGN
            return

        # RTS
        if (self.instr & 0o177770) == 0o000200:
            self.R[7] = self.R[d & 7]
            self.R[d & 7] = self.pop()
            return
    
        # TODO: what are these?
        bits = self.instr & 0o177400
        if bits == 0o000400:
            self.branch(o)
            return
        elif bits == 0o001000:
            if not (self.PS & PDP11.FLAGZ):
                self.branch(o)
            return
        elif bits == 0o001400:
            if self.PS & PDP11.FLAGZ:
                self.branch(o)
            return
        elif bits == 0o002000:
            if not self._xor(self.PS & PDP11.FLAGN, self.PS & PDP11.FLAGV):
                self.branch(o)
            return
        elif bits == 0o002400:
            if self._xor(self.PS & PDP11.FLAGN, self.PS & PDP11.FLAGV):
                self.branch(o)
            return
        elif bits == 0o003000:
            if not self._xor(self.PS & PDP11.FLAGN, self.PS & PDP11.FLAGV) and not (self.PS & PDP11.FLAGZ):
                self.branch(o)
            return
        elif bits == 0o003400:
            if self._xor(self.PS & PDP11.FLAGN, self.PS & PDP11.FLAGV) or (self.PS & PDP11.FLAGZ):
                self.branch(o)
            return
        elif bits == 0o100000:
            if not (self.PS & PDP11.FLAGN):
                self.branch(o)
            return
        elif bits == 0o100400:
            if self.PS & PDP11.FLAGN:
                self.branch(o)
            return
        elif bits == 0o101000:
            if not (self.PS & PDP11.FLAGC) and not (self.PS & PDP11.FLAGZ):
                self.branch(o)
            return
        elif bits == 0o101400:
            if (self.PS & PDP11.FLAGC) or (self.PS & PDP11.FLAGZ):
                self.branch(o)
            return
        elif bits == 0o102000:
            if not (self.PS & PDP11.FLAGV):
                self.branch(o)
            return
        elif bits == 0o102400:
            if self.PS & PDP11.FLAGV:
                self.branch(o)
            return
        elif bits == 0o103000:
            if not (self.PS & PDP11.FLAGC):
                self.branch(o)
            return
        elif bits == 0o103400:
            if self.PS & PDP11.FLAGC:
                self.branch(o)
            return

        # EMT TRAP IOT BPT
        if (self.instr & 0o177000) == 0o104000 or self.instr == 3 or self.instr == 4:
            #var vec, prev;
            if (self.instr & 0o177400) == 0o104000:
                vec = 0o30
            elif (self.instr & 0o177400) == 0o104400:
                vec = 0o34
            elif self.instr == 3:
                vec = 0o14
            else:
                vec = 0o20
            prev = self.PS
            self.switchmode(False)
            self.push(prev)
            self.push(self.R[7])
            self.R[7] = self.memory[vec>>1]
            self.PS = self.memory[(vec>>1)+1]
            if self.prevuser:
                self.PS |= (1<<13) | (1<<12)
            return

        # CL?, SE?
        if (self.instr & 0o177740) == 0o240:
            if self.instr & 0o20:
                self.PS |= self.instr & 0o17
            else:
                self.PS &= ~(self.instr & 0o17)
            return

        # HALT / WAIT / RTI / RTT / RESET / SETD
        bits = self.instr
        if bits == 0o000000: # HALT
            if not self.curuser:
                self.writedebug("HALT\n")
                self.printstate()
                self.stop()
                return
        elif bits == 0o000001: # WAIT
            time.sleep(0.001)
            if not self.curuser:
                self.running.clear()
                return
        elif bits == 0o000002 or bits == 0o000006: # RTI / RTT
            self.R[7] = self.pop()
            val = self.pop()
            if self.curuser:
                val &= 0o47
                val |= self.PS & 0o177730
            self.physwrite16(0o777776, val)
            return
        elif bits == 0o000005: # RESET
            if self.curuser:
                return
            self.terminal.clear()
            self.rk.reset()
            return
        elif bits == 0o170011: # SETD ; not needed by UNIX, but used; therefore ignored
            return
        raise(Trap(INT.INVAL, "invalid instruction: " + self.disasm(ia)))


    def run(self):
        while not self.cpu_stop.is_set():
            try:
                self.step()

                self.running.wait()

                # Handle interrupts
                if not self.interrupts.empty():
                    priority_level = ((self.PS >> 5) & 7)
                    if self.last_interrupt_priority > priority_level:
                        inter = self.interrupts.get()
                        # this is fixed according to Wikipedia description from >= to >
                        if inter.pri > priority_level:
                            self.handleinterrupt(inter.vec)
                            self.last_interrupt_priority = INT.MAX_PRIORITY
                        else:
                            # remember this "unprocessed" interrupt's priority for minor optimization
                            self.last_interrupt_priority = inter.pri
                            self.interrupts.put(inter)

                # Show iterations per seconds
                # TODO: move into clock thread
                if self.ips >= 150000:
                    now = time.time()
                    self.terminal.show_ips(int(self.ips/(now - self.lastTime)))
                    self.ips = 0
                    self.lastTime = now

            except Trap as e:
                self.trapat(e.num, str(e))

            if self.prdebug:
                self.printstate()
                time.sleep(1)

        print('- CPU stopped')

    def start_cpu(self):
        self.cpu_stop = threading.Event()
        self.cpu_thread = threading.Thread(target=self.run)
        self.cpu_thread.daemon = True
        self.cpu_thread.start()

        self.clock_stop = threading.Event()
        self.clock_thread = threading.Thread(target=self.clock)
        self.clock_thread.daemon = True
        self.clock_thread.start()

    def stop_cpu(self):
        print('Stopping CPU...')
        self.clock_stop.set()
        self.cpu_stop.set()

if __name__=='__main__':
    pdp11 = PDP11()
    pdp11.start_cpu()
    pdp11.terminal.mainloop()
