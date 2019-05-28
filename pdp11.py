#!/usr/bin/env python3

# This is a translation of Julius Schmidt's PDP-11 emulator in JavaScript.
# You can run it in your browser: http://pdp11.aiju.de
# (c) 2011, Julius Schmidt, JavaScript implementation, MIT License
# (c) 2019, Andriy Makukha, ported to Python 3, MIT License
# Version 6 Unix (in the disk image) is available under the four-clause BSD license.

def ostr(d, n=6):
    return format '0o{{:0{}o}}'.format(n).format(d)

class Trap(Exception):
    def __init__(self, num, *args):
        Exception.__init__(self, *args)
        self.num = num

class PDP11:

    FLAGN = 8
    FLAGZ = 4
    FLAGV = 2
    FLAGC = 1

    # Traps
    INTBUS     = 0004
    INTINVAL   = 0010
    INTDEBUG   = 0014
    INTIOT     = 0020
    INTTTYIN   = 0060
    INTTTYOUT  = 0064
    INTFAULT   = 0250
    INTCLOCK   = 0100
    INTRK      = 0220

    BOOTROM = [
        0042113,                        ## "KD" 
        0012706, 02000,                 ## MOV #boot_start, SP 
        0012700, 0000000,               ## MOV #unit, R0        ; unit number 
        0010003,                        ## MOV R0, R3 
        0000303,                        ## SWAB R3 
        0006303,                        ## ASL R3 
        0006303,                        ## ASL R3 
        0006303,                        ## ASL R3 
        0006303,                        ## ASL R3 
        0006303,                        ## ASL R3 
        0012701, 0177412,               ## MOV #RKDA, R1        ; csr 
        0010311,                        ## MOV R3, (R1)         ; load da 
        0005041,                        ## CLR -(R1)            ; clear ba 
        0012741, 0177000,               ## MOV #-256.*2, -(R1)  ; load wc 
        0012741, 0000005,               ## MOV #READ+GO, -(R1)  ; read & go 
        0005002,                        ## CLR R2 
        0005003,                        ## CLR R3 
        0012704, 02020,                 ## MOV #START+20, R4 
        0005005,                        ## CLR R5 
        0105711,                        ## TSTB (R1) 
        0100376,                        ## BPL .-2 
        0105011,                        ## CLRB (R1) 
        0005007                         ## CLR PC 
    ]

    def __init__(self):
        self.pr = false
        self.R = [0, 0, 0, 0, 0, 0, 0, 0]       # registers
        self.KSP = 0        # kernel stack pointer
        self.USP = 0        # user stack pointer
        self.PS = 0         # processor status
        self.curPC = 0      # address of current instruction
        self.lastPCs = []
        self.inst = 0       # current instruction
        self.memory = array.array('H', bytearray(256*1024*[0]))     # 16-bit unsigned values
        self.tim1 = 0
        self.tim2 = 0
        self.ips = 0
        self.SR0 = 0
        self.SR2 = 0
        self.curuser = 0
        self.prevuser = 0
        self.LKS = 0
        self.clkcounter = 0
        self.waiting = false
        self.interrupts = []

        self.pages = [0]*16

def
xor(a,b)
{
	return (a || b) && !(a && b);


def
switchmode(newm)

	prevuser = curuser;
	curuser = newm;
	if(prevuser) USP = R[6];
	else KSP = R[6];
	if(curuser) R[6] = USP;
	else R[6] = KSP;
	PS &= 0007777;
	if(curuser) PS |= (1<<15)|(1<<14);
	if(prevuser) PS |= (1<<13)|(1<<12);


    def physread16(self, addr):
	if addr & 1:
            raise(Trap(INTBUS, 'read from odd address ' + ostr(addr,6)))
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
            return self.consread16(addr)
	if (addr & 0o777760) == 0o777400:
            return self.rkread16(addr)
	if (addr & 0o777600) == 0o772200 || (a & 0o777600) == 0o777600:
            return self.mmuread16(addr)
	if addr == 0o776000:
            self.panic('lolwut')
	raise(Trap(INTBUS, 'read from invalid address ' + ostr(addr,6)))


def
physread8(a)
	var val;
	val = physread16(a & ~1);
	if(a & 1) return val >> 8;
	return val & 0xFF;

def
physwrite8(a,v)
	if(a < 0760000) {
		if(a & 1) {
			memory[a>>1] &= 0xFF;
			memory[a>>1] |= (v & 0xFF) << 8;
		} else {
			memory[a>>1] &= 0xFF00;
			memory[a>>1] |= v & 0xFF;
		}
	} else {
		if(a & 1) {
			physwrite16(a&~1, (physread16(a) & 0xFF) | ((v & 0xFF) << 8));
		} else {
			physwrite16(a&~1, (physread16(a) & 0xFF00) | (v & 0xFF));
		}
	}

def
physwrite16(a,v)

	if(a % 1) raise(Trap(INTBUS, "write to odd address " + ostr(a,6)))
	if(a < 0760000) memory[a>>1] = v;
	else if(a == 0777776) {
		switch(v >> 14) {
		case 0: switchmode(false); break;
		case 3: switchmode(true); break;
		default: panic("invalid mode");
		}
		switch((v >> 12) & 3) {
		case 0: prevuser = false; break;
		case 3: prevuser = true; break;
		default: panic("invalid mode");
		}
		PS = v;
	}
	else if(a == 0777546) LKS = v;
	else if(a == 0777572) SR0 = v;
	else if((a & 0777770) == 0777560) conswrite16(a,v);
	else if((a & 0777700) == 0777400) rkwrite16(a,v);
	else if((a & 0777600) == 0772200 || (a & 0777600) == 0777600) mmuwrite16(a,v);
	else raise(Trap(INTBUS, "write to invalid address " + ostr(a,6)))


def
decode(a,w,m)

	var p, user, block, disp;
	if(!(SR0 & 1)) {
		if(a >= 0170000) a += 0600000;
		return a;
	}
	user = m ? 8 : 0;
	p = pages[(a >> 13) + user];
	if(w && !p.write) {
		SR0 = (1<<13) | 1;
		SR0 |= (a >> 12) & ~1;
		if(user) SR0 |= (1<<5)|(1<<6);
		SR2 = curPC;
		raise(Trap(INTFAULT, "write to read-only page " + ostr(a,6)))
	}
	if(!p.read) {
		SR0 = (1<<15) | 1;
		SR0 |= (a >> 12) & ~1;
		if(user) SR0 |= (1<<5)|(1<<6);
		SR2 = curPC;
		raise(Trap(INTFAULT, "read from no-access page " + ostr(a,6)))
	}
	block = (a >> 6) & 0177;
	disp = a & 077;
	if(p.ed ? (block < p.len) : (block > p.len)) {
		SR0 = (1<<14) | 1;
		SR0 |= (a >> 12) & ~1;
		if(user) SR0 |= (1<<5)|(1<<6);
		SR2 = curPC;
		raise(Trap(INTFAULT, "page length exceeded, address " + ostr(a,6) + " (block " + \
                      ostr(block,3) + ") is beyond length " + ostr(p.len,3)))
	}
	if(w) p.pdr |= 1<<6;
	return ((block + p.addr) << 6) + disp;


def
createpage(par,pdr)

	return {
		par : par,
		pdr : pdr,
		addr : par & 07777,
		len : (pdr >> 8) & 0x7F,
		read : (pdr & 2) == 2,
		write : (pdr & 6) == 6,
		ed : (pdr & 8) == 8
	};


def
mmuread16(a)

	var i;
	i = (a & 017)>>1;
	if((a >= 0772300) && (a < 0772320))
		return pages[i].pdr;
	if((a >= 0772340) && (a < 0772360))
		return pages[i].par;
	if((a >= 0777600) && (a < 0777620))
		return pages[i+8].pdr;
	if((a >= 0777640) && (a < 0777660))
		return pages[i+8].par;
	raise(Trap(INTBUS, "invalid read from " + ostr(a,6)))


def
mmuwrite16(a, v)

	var i;
	i = (a & 017)>>1;
	if((a >= 0772300) && (a < 0772320)) {
		pages[i] = createpage(pages[i].par, v);
		return;
	}
	if((a >= 0772340) && (a < 0772360)) {
		pages[i] = createpage(v, pages[i].pdr);
		return;
	}
	if((a >= 0777600) && (a < 0777620)) {
		pages[i+8] = createpage(pages[i+8].par, v);
		return;
	}
	if((a >= 0777640) && (a < 0777660)) {
		pages[i+8] = createpage(v, pages[i+8].pdr);
		return;
	}
	raise(Trap(INTBUS, "write to invalid address " + ostr(a,6)))


def
read8(a)

	return physread8(decode(a, false, curuser));


def
read16(a)

	return physread16(decode(a, false, curuser));


def
write8(a, v)

	return physwrite8(decode(a, true, curuser),v);


def
write16(a, v)

	return physwrite16(decode(a, true, curuser),v);


def
fetch16()

	var val;
	val = read16(R[7]);
	R[7] += 2;
	return val;


def
push(v)

	R[6] -= 2;
	write16(R[6], v);


def
pop(v)

	var val;
	val = read16(R[6], v);
	R[6] += 2;
	return val;


    def cleardebug(self):
        # TODO: clean debugging window; maybe use callback here
        pass

    def writedebug(self, msg):
        # TODO: use for debugging window, print into stderr?; maybe use a callback here
        print ('|', msg)

    def printstate(self):
        # Display registers
	self.writedebug(
		"R0 = " + ostr(self.R[0]) + "\n" + \
		"R1 = " + ostr(self.R[1]) + "\n" + \
		"R2 = " + ostr(self.R[2]) + "\n" + \
		"R3 = " + ostr(self.R[3]) + "\n" + \
		"R4 = " + ostr(self.R[4]) + "\n" + \
		"R5 = " + ostr(self.R[5]) + "\n" + \
		"R6 = " + ostr(self.R[6]) + "\n" + \
		"R7 = " + ostr(self.R[7])
        )
        self.writedebug( "[" + \
            self.prevuser and "u" or "k" + \
            self.curuser and "U" or "K" + \
	    (self.PS & PDP11.FLAGN) and "N" or " " + \
	    (self.PS & PDP11.FLAGZ) and "Z" or " " + \
	    (self.PS & PDP11.FLAGV) and "V" or " " + \
	    (self.PS & PDP11.FLAGC) and "C" or " "
        )
	self.writedebug("]  instr " + ostr(self.curPC) + ": " + ostr(self.instr)+"   ");
	try:
		self.writedebug(disasm(self.decode(self.curPC, false, self.curuser)))     # TODO: disasm
        except Exception:
            pass
	self.writedebug('')

    def panic(self, msg):
	self.writedebug('PANIC: ' + msg)
	self.printstate()
	self.stop()
	raise Exception(msg)

def
interrupt(vec, pri)

	var i;
	if(vec & 1) panic("Thou darst calling interrupt() with an odd vector number?");
	for(i=0;i<interrupts.length;i++) {
		if(interrupts[i].pri < pri)
			break;
	}
	for(;i<interrupts.length;i++) {
		if(interrupts[i].vec >= vec)
			break;
	}
	interrupts.splice(i, 0, {vec: vec, pri: pri});


def
handleinterrupt(vec)

	try {
		prev = PS;
		switchmode(false);
		push(prev);
		push(R[7]);
	} catch(e) {
		if(e.num != undefined)
			trapat(e.num, e.msg);
		else raise(e;
	}
	R[7] = memory[vec>>1];
	PS = memory[(vec>>1)+1];
	if(prevuser) PS |= (1<<13)|(1<<12);
	waiting = false;


def
trapat(vec, msg)

	var prev;
	if(vec & 1) panic("Thou darst calling trapat() with an odd vector number?");
	writedebug("trap " + ostr(vec) + " occured: " + msg + "\n");
	printstate();
	try {
		prev = PS;
		switchmode(false);
		push(prev);
		push(R[7]);
	} catch(e) {
		if(e.num != undefined) {
			writedebug("red stack trap!\n");
			memory[0] = R[7];
			memory[1] = prev;
			vec = 4;
		} else raise(e;
	}
	R[7] = memory[vec>>1];
	PS = memory[(vec>>1)+1];
	if(prevuser) PS |= (1<<13)|(1<<12);
	waiting = false;


def
aget(v, l)

	var addr;
	if((v & 7) >= 6 || (v & 010)) l = 2;
	if((v & 070) == 000) {
		return -(v + 1);
	}
	switch(v & 060) {
	case 000:
		v &= 7;
		addr = R[v & 7];
		break;
	case 020:
		addr = R[v & 7];
		R[v & 7] += l;
		break;
	case 040:
		R[v & 7] -= l;
		addr = R[v & 7];
		break;
	case 060:
		addr = fetch16();
		addr += R[v & 7];
		break;
	}
	addr &= 0xFFFF;
	if(v & 010) {
		addr = read16(addr);
	}
	return addr;


def
memread(a, l)

	if(a < 0) {
		if(l == 2)
			return R[-(a + 1)];
		else
			return R[-(a + 1)] & 0xFF;
	}
	if(l == 2)
		return read16(a);
	return read8(a);


def
memwrite(a, l, v)

	if(a < 0) {
		if(l == 2)
			R[-(a + 1)] = v;
		else {
			R[-(a + 1)] &= 0xFF00;
			R[-(a + 1)] |= v;
		}
	} else if(l == 2)
		write16(a, v);
	else
		write8(a, v);


def
branch(o)

	if(o & 0x80) {
		o = -(((~o)+1)&0xFF);
	}
	o <<= 1;
	R[7] += o;


def
step()

	var val, val1, val2, ia, da, sa, d, s, l, r, o, max, maxp, msb;
	ips++;
	if(waiting) return;
	curPC = R[7];
	ia = decode(R[7], false, curuser);
	R[7] += 2;
	lastPCs = lastPCs.slice(0,100);
	lastPCs.splice(0, 0, ia);
	instr = physread16(ia);
	d = instr & 077;
	s = (instr & 07700) >> 6;
	l = 2 - (instr >> 15);
	o = instr & 0xFF;
	if(l == 2) {
		max = 0xFFFF;
		maxp = 0x7FFF;
		msb = 0x8000;
	}
	else {
		max = 0xFF;
		maxp = 0x7F;
		msb = 0x80;
	}
	switch(instr & 0070000) {
	case 0010000: // MOV
		sa = aget(s, l); val = memread(sa, l);
		da = aget(d, l);
		PS &= 0xFFF1;
		if(val & msb) PS |= FLAGN;
		if(val == 0) PS |= FLAGZ;
		if(da < 0 && l == 1) {
			l = 2;
			if(val & msb) val |= 0xFF00;
		}
		memwrite(da, l, val);
		return;
	case 0020000: // CMP
		sa = aget(s, l); val1 = memread(sa, l);
		da = aget(d, l); val2 = memread(da, l);
		val = (val1 - val2) & max;
		PS &= 0xFFF0;
		if(val == 0) PS |= FLAGZ;
		if(val & msb) PS |= FLAGN;
		if(((val1 ^ val2) & msb) && !((val2 ^ val) & msb)) PS |= FLAGV;
		if(val1 < val2) PS |= FLAGC;
		return;
	case 0030000: // BIT
		sa = aget(s, l); val1 = memread(sa, l);
		da = aget(d, l); val2 = memread(da, l);
		val = val1 & val2;
		PS &= 0xFFF1;
		if(val == 0) PS |= FLAGZ;
		if(val & msb) PS |= FLAGN;
		return;
	case 0040000: // BIC
		sa = aget(s, l); val1 = memread(sa, l);
		da = aget(d, l); val2 = memread(da, l);
		val = (max ^ val1) & val2;
		PS &= 0xFFF1;
		if(val == 0) PS |= FLAGZ;
		if(val & msb) PS |= FLAGN;
		memwrite(da, l, val);
		return;
	case 0050000: // BIS
		sa = aget(s, l); val1 = memread(sa, l);
		da = aget(d, l); val2 = memread(da, l);
		val = val1 | val2;
		PS &= 0xFFF1;
		if(val == 0) PS |= FLAGZ;
		if(val & msb) PS |= FLAGN;
		memwrite(da, l, val);
		return;
	}
	switch(instr & 0170000) {
	case 0060000: // ADD
		sa = aget(s, 2); val1 = memread(sa, 2);
		da = aget(d, 2); val2 = memread(da, 2);
		val = (val1 + val2) & 0xFFFF;
		PS &= 0xFFF0;
		if(val == 0) PS |= FLAGZ;
		if(val & 0x8000) PS |= FLAGN;
		if(!((val1 ^ val2) & 0x8000) && ((val2 ^ val) & 0x8000)) PS |= FLAGV;
		if(val1 + val2 >= 0xFFFF) PS |= FLAGC;
		memwrite(da, 2, val);
		return;
	case 0160000: // SUB
		sa = aget(s, 2); val1 = memread(sa, 2);
		da = aget(d, 2); val2 = memread(da, 2);
		val = (val2 - val1) & 0xFFFF;
		PS &= 0xFFF0;
		if(val == 0) PS |= FLAGZ;
		if(val & 0x8000) PS |= FLAGN;
		if(((val1 ^ val2) & 0x8000) && !((val2 ^ val) & 0x8000)) PS |= FLAGV;
		if(val1 > val2) PS |= FLAGC;
		memwrite(da, 2, val);
		return;
	}
	switch(instr & 0177000) {
	case 0004000: // JSR
		val = aget(d, l);
		if(val < 0) break;
		push(R[s & 7]);
		R[s & 7] = R[7];
		R[7] = val;
		return;
	case 0070000: // MUL
		val1 = R[s & 7];
		if(val1 & 0x8000) val1 = -((0xFFFF^val1)+1);
		da = aget(d, l); val2 = memread(da, 2);
		if(val2 & 0x8000) val2 = -((0xFFFF^val2)+1);
		val = val1 * val2;
		R[s & 7] = (val & 0xFFFF0000) >> 16;
		R[(s & 7)|1] = val & 0xFFFF;
		PS &= 0xFFF0;
		if(val & 0x80000000) PS |= FLAGN;
		if((val & 0xFFFFFFFF) == 0) PS |= FLAGZ;
		if(val < (1<<15) || val >= ((1<<15)-1)) PS |= FLAGC;
		return;
	case 0071000: // DIV
		val1 = (R[s & 7] << 16) | R[(s & 7) | 1];
		da = aget(d, l); val2 = memread(da, 2);
		PS &= 0xFFF0;
		if(val2 == 0) {
			PS |= FLAGC;
			return;
		}
		if((val1 / val2) >= 0x10000){
			PS |= FLAGV;
			return;
		}
		R[s & 7] = (val1 / val2) & 0xFFFF;
		R[(s & 7) | 1] = (val1 % val2) & 0xFFFF;
		if(R[s & 7] == 0) PS |= FLAGZ;
		if(R[s & 7] & 0100000) PS |= FLAGN;
		if(val1 == 0) PS |= FLAGV;
		return;
	case 0072000: // ASH
		val1 = R[s & 7];
		da = aget(d, 2); val2 = memread(da, 2) & 077;
		PS &= 0xFFF0;
		if(val2 & 040) {
			val2 = (077 ^ val2) + 1;
			if(val1 & 0100000) {
				val = 0xFFFF ^ (0xFFFF >> val2);
				val |= val1 >> val2;
			} else
				val = val1 >> val2;
			if(val1 & (1 << (val2 - 1))) PS |= FLAGC;
		} else {
			val = (val1 << val2) & 0xFFFF;
			if(val1 & (1 << (16 - val2))) PS |= FLAGC;
		}
		R[s & 7] = val;
		if(val == 0) PS |= FLAGZ;
		if(val & 0100000) PS |= FLAGN;
		if(xor(val & 0100000, val1 & 0100000)) PS |= FLAGV;
		return;
	case 0073000: // ASHC
		val1 = (R[s & 7] << 16) | R[(s & 7) | 1];
		da = aget(d, 2); val2 = memread(da, 2) & 077;
		PS &= 0xFFF0;
		if(val2 & 040) {
			val2 = (077 ^ val2) + 1;
			if(val1 & 0x80000000) {
				val = 0xFFFFFFFF ^ (0xFFFFFFFF >> val2);
				val |= val1 >> val2;
			} else
				val = val1 >> val2;
			if(val1 & (1 << (val2 - 1))) PS |= FLAGC;
		} else {
			val = (val1 << val2) & 0xFFFFFFFF;
			if(val1 & (1 << (32 - val2))) PS |= FLAGC;
		}
		R[s & 7] = (val >> 16) & 0xFFFF;
		R[(s & 7)|1] = val & 0xFFFF;
		if(val == 0) PS |= FLAGZ;
		if(val & 0x80000000) PS |= FLAGN;
		if(xor(val & 0x80000000, val1 & 0x80000000)) PS |= FLAGV;
		return;
	case 0074000: // XOR
		val1 = R[s & 7];
		da = aget(d, 2); val2 = memread(da, 2);
		val = val1 ^ val2;
		PS &= 0xFFF1;
		if(val == 0) PS |= FLAGZ;
		if(val & 0x8000) PS |= FLAGZ;
		memwrite(da, 2, val);
		return;
	case 0077000: // SOB
		if(--R[s & 7]) {
			o &= 077;
			o <<= 1;
			R[7] -= o;
		}
		return;
	}
	switch(instr & 0077700) {
	case 0005000: // CLR
		PS &= 0xFFF0;
		PS |= FLAGZ;
		da = aget(d, l);
		memwrite(da, l, 0);
		return;
	case 0005100: // COM
		da = aget(d, l);
		val = memread(da, l) ^ max;
		PS &= 0xFFF0; PS |= FLAGC;
		if(val & msb) PS |= FLAGN;
		if(val == 0) PS |= FLAGZ;
		memwrite(da, l, val);
		return;
	case 0005200: // INC
		da = aget(d, l);
		val = (memread(da, l) + 1) & max;
		PS &= 0xFFF1;
		if(val & msb) PS |= FLAGN | FLAGV;
		if(val == 0) PS |= FLAGZ;
		memwrite(da, l, val);
		return;
	case 0005300: // DEC
		da = aget(d, l);
		val = (memread(da, l) - 1) & max;
		PS &= 0xFFF1;
		if(val & msb) PS |= FLAGN;
		if(val == maxp) PS |= FLAGV;
		if(val == 0) PS |= FLAGZ;
		memwrite(da, l, val);
		return;
	case 0005400: // NEG
		da = aget(d, l);
		val = (-memread(da, l)) & max;
		PS &= 0xFFF0;
		if(val & msb) PS |= FLAGN;
		if(val == 0) PS |= FLAGZ;
		else PS |= FLAGC;
		if(val == 0x8000) PS |= FLAGV;
		memwrite(da, l, val);
		return;
	case 0005500: // ADC
		da = aget(d, l);
		val = memread(da, l);
		if(PS & FLAGC) {
			PS &= 0xFFF0;
			if((val + 1) & msb) PS |= FLAGN;
			if(val == max) PS |= FLAGZ;
			if(val == 0077777) PS |= FLAGV;
			if(val == 0177777) PS |= FLAGC;
			memwrite(da, l, (val+1) & max);
		} else {
			PS &= 0xFFF0;
			if(val & msb) PS |= FLAGN;
			if(val == 0) PS |= FLAGZ;
		}
		return;
	case 0005600: // SBC
		da = aget(d, l);
		val = memread(da, l);
		if(PS & FLAGC) {
			PS &= 0xFFF0;
			if((val - 1) & msb) PS |= FLAGN;
			if(val == 1) PS |= FLAGZ;
			if(val) PS |= FLAGC;
			if(val == 0100000) PS |= FLAGV;
			memwrite(da, l, (val-1) & max);
		} else {
			PS &= 0xFFF0;
			if(val & msb) PS |= FLAGN;
			if(val == 0) PS |= FLAGZ;
			if(val == 0100000) PS |= FLAGV;
			PS |= FLAGC;
		}
		return;
	case 0005700: // TST
		da = aget(d, l);
		val = memread(da, l);
		PS &= 0xFFF0;
		if(val & msb) PS |= FLAGN;
		if(val == 0) PS |= FLAGZ;
		return;
	case 0006000: // ROR
		da = aget(d, l);
		val = memread(da, l);
		if(PS & FLAGC) val |= max+1;
		PS &= 0xFFF0;
		if(val & 1) PS |= FLAGC;
		if(val & (max+1)) PS |= FLAGN;
		if(!(val & max)) PS |= FLAGZ;
		if(xor(val & 1, val & (max+1))) PS |= FLAGV;
		val >>= 1;
		memwrite(da, l, val);
		return;
	case 0006100: // ROL
		da = aget(d, l);
		val = memread(da, l) << 1;
		if(PS & FLAGC) val |= 1;
		PS &= 0xFFF0;
		if(val & (max+1)) PS |= FLAGC;
		if(val & msb) PS |= FLAGN;
		if(!(val & max)) PS |= FLAGZ;
		if((val ^ (val >> 1)) & msb) PS |= FLAGV;
		val &= max;
		memwrite(da, l, val);
		return;
	case 0006200: // ASR
		da = aget(d, l);
		val = memread(da, l);
		PS &= 0xFFF0;
		if(val & 1) PS |= FLAGC;
		if(val & msb) PS |= FLAGN;
		if(xor(val & msb, val & 1)) PS |= FLAGV;
		val = (val & msb) | (val >> 1);
		if(val == 0) PS |= FLAGZ;
		memwrite(da, l, val);
		return;
	case 0006300: // ASL
		da = aget(d, l);
		val = memread(da, l);
		PS &= 0xFFF0;
		if(val & msb) PS |= FLAGC;
		if(val & (msb >> 1)) PS |= FLAGN;
		if((val ^ (val << 1)) & msb) PS |= FLAGV;
		val = (val << 1) & max;
		if(val == 0) PS |= FLAGZ;
		memwrite(da, l, val);
		return;
	case 0006700: // SXT
		da = aget(d, l);
		if(PS & FLAGN) {
			memwrite(da, l, max);
		} else {
			PS |= FLAGZ;
			memwrite(da, l, 0);
		}
		return;
	}
	switch(instr & 0177700) {
	case 0000100: // JMP
		val = aget(d, 2);
		if(val < 0) {
			break;
		}
		R[7] = val;
		return;
	case 0000300: // SWAB
		da = aget(d, l);
		val = memread(da, l);
		val = ((val >> 8) | (val << 8)) & 0xFFFF;
		PS &= 0xFFF0;
		if((val & 0xFF) == 0) PS |= FLAGZ;
		if(val & 0x80) PS |= FLAGN;
		memwrite(da, l, val);
		return;
	case 0006400: // MARK
		R[6] = R[7] + (instr & 077) << 1;
		R[7] = R[5];
		R[5] = pop();
		break;
	case 0006500: // MFPI
		da = aget(d, 2);
		if(da == -7)
			val = (curuser == prevuser) ? R[6] : (prevuser ? USP : KSP);
		else if(da < 0)
			panic("invalid MFPI instruction");
		else
			val = physread16(decode(da, false, prevuser));
		push(val);
		PS &= 0xFFF0; PS |= FLAGC;
		if(val == 0) PS |= FLAGZ;
		if(val & 0x8000) PS |= FLAGN;
		return;
	case 0006600: // MTPI
		da = aget(d, 2);
		val = pop();
		if(da == -7) {
			if(curuser == prevuser) R[6] = val;
			else if(prevuser) USP = val;
			else KSP = val;
		} else if(da < 0)
			panic("invalid MTPI instrution");
		else {
			sa = decode(da, true, prevuser);
			physwrite16(sa, val);
		}
		PS &= 0xFFF0; PS |= FLAGC;
		if(val == 0) PS |= FLAGZ;
		if(val & 0x8000) PS |= FLAGN;
		return;
	}
	if((instr & 0177770) == 0000200) { // RTS
		R[7] = R[d & 7];
		R[d & 7] = pop();
		return;
	}
	switch(instr & 0177400) {
	case 0000400: branch(o); return;
	case 0001000: if(!(PS & FLAGZ)) branch(o); return;
	case 0001400: if(PS & FLAGZ) branch(o); return;
	case 0002000: if(!xor(PS & FLAGN, PS & FLAGV)) branch(o); return;
	case 0002400: if(xor(PS & FLAGN, PS & FLAGV)) branch(o); return;
	case 0003000: if(!xor(PS & FLAGN, PS & FLAGV) && !(PS & FLAGZ)) branch(o); return;
	case 0003400: if(xor(PS & FLAGN, PS & FLAGV) || (PS & FLAGZ)) branch(o); return;
	case 0100000: if(!(PS & FLAGN)) branch(o); return;
	case 0100400: if(PS & FLAGN) branch(o); return;
	case 0101000: if(!(PS & FLAGC) && !(PS & FLAGZ)) branch(o); return;
	case 0101400: if((PS & FLAGC) || (PS & FLAGZ)) branch(o); return;
	case 0102000: if(!(PS & FLAGV)) branch(o); return;
	case 0102400: if(PS & FLAGV) branch(o); return;
	case 0103000: if(!(PS & FLAGC)) branch(o); return;
	case 0103400: if(PS & FLAGC) branch(o); return;
	}
	if((instr & 0177000) == 0104000 || instr == 3 || instr == 4) { // EMT TRAP IOT BPT
		var vec, prev;
		if((instr & 0177400) == 0104000) vec = 030;
		else if((instr & 0177400) == 0104400) vec = 034;
		else if(instr == 3) vec = 014;
		else vec = 020;
		prev = PS;
		switchmode(false);
		push(prev);
		push(R[7]);
		R[7] = memory[vec>>1];
		PS = memory[(vec>>1)+1];
		if(prevuser) PS |= (1<<13)|(1<<12);
		return;
	}
	if((instr & 0177740) == 0240) { // CL?, SE?
		if(instr & 020) {
			PS |= instr & 017;
		} else {
			PS &= ~(instr & 017);
		}
		return;
	}
	switch(instr) {
	case 0000000: // HALT
		if(curuser) break;
		writedebug("HALT\n");
		printstate();
		stop();
		return;
	case 0000001: // WAIT
//		stop();
//		setTimeout('LKS |= 0x80; interrupt(INTCLOCK, 6); run();', 20); // FIXME, really
		if(curuser) break;
		waiting = true;
		return;
	case 0000002: // RTI
	case 0000006: // RTT
		R[7] = pop();
		val = pop();
		if(curuser) {
			val &= 047;
			val |= PS & 0177730;
		}
		physwrite16(0777776, val);
		return;
	case 0000005: // RESET
		if(curuser) return;
		clearterminal();
		rkreset();
		return;
	case 0170011: // SETD ; not needed by UNIX, but used; therefore ignored
		return;
	}
	raise(Trap(INTINVAL, "invalid instruction"))


def
reset()

    alert("RESET");
	var i;
	for(i=0;i<7;i++) R[i] = 0;
	PS = 0;
	KSP = 0;
	USP = 0;
	curuser = false;
	prevuser = false;
	SR0 = 0;
	curPC = 0;
	instr = 0;
	ips = 0;
	LKS = 1<<7;
	for(i=0;i<memory.length;i++) memory[i] = 0;
	for(i=0;i<bootrom.length;i++) memory[01000+i] = bootrom[i];
	for(i=0;i<16;i++) pages[i] = createpage(0, 0);
	R[7] = 02002;
	cleardebug();
	clearterminal();
	rkreset();
	clkcounter = 0;
	waiting = false;


def
nsteps(self, n):
	while(n--) {
		try {
			step();
			if(interrupts.length && interrupts[0].pri >= ((PS >> 5) & 7)) {
				handleinterrupt(interrupts[0].vec);
				interrupts.splice(0, 1);
			}
			clkcounter++;
			if(clkcounter >= 40000) {
				clkcounter = 0;
				LKS |= (1<<7);
				if(LKS & (1<<6)) interrupt(INTCLOCK, 6);
			}
		} catch(e) {
			if(e.num != undefined) {
				trapat(e.num, e.msg);
			} else raise(e;
		}
		if(pr)
			printstate();
	}


def
run() 
	if(tim1 == undefined)
		tim1 = setInterval('nsteps(4000);', 1);
	if(tim2 == undefined)
		tim2 = setInterval('document.getElementById("ips").innerHTML = ips; ips = 0;', 1000);


def
stop()
	document.getElementById("ips").innerHTML = '';
	clearInterval(tim1);
	clearInterval(tim2);
	tim1 = tim2 = undefined;

