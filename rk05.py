#!/usr/bin/env python3

# This is a translation of Julius Schmidt's PDP-11 emulator in JavaScript.
# You can run that one in your browser: http://pdp11.aiju.de
# (c) 2011, Julius Schmidt, JavaScript implementation, MIT License
# (c) 2019, Andriy Makukha, ported to Python 3, MIT License
# Version 6 Unix (in the disk image) is available under the four-clause BSD license.

import time, array, threading
from interrupt import Interrupt
from unix_v6_fs import UnixV6FileSystem

class System:
    
    def __init__(self):
        self.memory = array.array('H', bytearray(256*1024*[0]))     # 16-bit unsigned values
        print ('Memory initialized')

    def interrupt(self, intr, y):
        pass

    def event(self, *evn):
        # 'rkbusy'  = document.getElementById('rkbusy').style.display = '';
        # 'rkready' = document.getElementById('rkbusy').style.display = 'none';
        pass

    def panic(self, msg):
        print ('PANIC: ', msg)

class RK05:
    '''RK05 was a magnetic disk drive produces by DEC. It stored approximately 2.5 MB on
    a 14 inch front-loading removable disk cartridge.'''

    EXPECTED_IMAGE_LENGTH = 2077696
    IMAGE_FILENAME = 'rk0.img'

    # Error codes
    RKOVR = (1<<14)
    RKNXD = (1<<7)
    RKNXC = (1<<6)
    RKNXS = (1<<5)
    
    def __init__(self, system):
        self.system = system
        #self.reinit()
    
    def reinit(self):
        # rkinit
        self.load_image(RK05.IMAGE_FILENAME)
       
        # Current "physical" position of the head
        self.drive = 0
        self.sector = 0
        self.surface = 0
        self.cylinder = 0

        self.reset()

    def save_image(self, filename):
        open(filename, 'wb').write(self.disk)

    def load_image(self, filename):
        self.disk = bytearray(open(filename, 'rb').read())
        if len(self.disk) != RK05.EXPECTED_IMAGE_LENGTH:
            self.system.panic('unexpected image length {} != {}'.format(len(self.disk), RK05.EXPECTED_IMAGE_LENGTH))
        print ('Disk image loaded:', len(self.disk))
        # TODO: extend image with free bytes, but also add those blocks to the free blocks chain
        #max_bytes = 0o313*0o14*2*512        # 4872 blocks, 2494464 bytes
        #if len(self.disk) < max_bytes:
        #    extend_by = max_bytes - len(self.disk)
        #    self.disk.extend(bytearray(extend_by*[0])) 
        #    print (' - free space:', extend_by)

    def start_sync_thread(self, unix_dir: 'path', local_dir: 'path'):
        self._unix_dir = unix_dir
        self._local_dir = local_dir
        
        self.sync_running = threading.Event()
        self.sync_finished = threading.Event()
        self.sync_finished.clear()

        self.sync_thread = threading.Thread(target=self.sync_method)
        self.sync_thread.daemon = True
        self.sync_thread.start()

    def sync_method(self):
        '''The purpose of this thread is to:
        1) exectute `sync` command before taking the filesystem snapshot
        2) pass the syncing work to the filesystem class using that snapshot
        3) wait for the syncing to finish, then take modified filesystem and replace the current one if Unix is not live
        '''
        if self.system.terminal.prompt_cnt > 0:
            self.sync_running.clear()
            self.system.terminal.queue_command('sync', self.sync_prompt)
            self.sync_running.wait()

        # TODO: check if filesystem is locked
        try:
            disk_snapshot = bytes(self.disk)
            self.fs = UnixV6FileSystem(disk_snapshot)
            self.fs.start_sync_thread(self._unix_dir, self._local_dir, self.system.terminal)

            self.fs.sync_finished.wait()

            # Replace current disk image with the synced one if Unix is not live
            if self.system.terminal.prompt_cnt == 0:
                self.fs.f.seek(0)
                disk = self.fs.f.read()
                if hash(disk_snapshot) != hash(disk) and disk_snapshot != disk:
                    self.disk = bytearray(disk)
                    self.system.writedebug('Disk image replaced with a synced one\n')

            msg = 'Unix directory {} synced with local directory {}\n'.format(self._unix_dir, self._local_dir)
            self.system.writedebug(msg)

        except Exception as e:
            raise e

    def sync_prompt(self, last_printed):
        self.sync_running.set()

    def reset(self):
        # Reset registers to default values
        self.DS = (1 << 11) | (1 << 7) | (1 << 6)
        self.ER = 0
        self.CS = 1 << 7
        self.WC = 0
        self.BA = 0
        self.DB = 0

    def read16(self, a):
        if a == 0o777400:
            return self.DS
        elif a ==0o0777402:
            return self.ER
        elif a == 0o0777404:
            return self.CS | ((self.BA & 0x30000) >> 12)
        elif a == 0o0777406:
            return self.WC
        elif a == 0o0777410:
            return self.BA & 0xFFFF
        elif a == 0o0777412:
            return (self.sector) | (self.surface << 4) | (self.cylinder << 5) | (self.drive << 13)
        else:
            self.system.panic('invalid read')

    def notready(self):
        #self.system.event('rkbusy')        # TODO
        self.DS &= ~(1<<6)
        self.CS &= ~(1<<7)

    def ready(self):
        #self.system.event('rkready')       # TODO
        self.DS |= 1<<6
        self.CS |= 1<<7

    def error(self, code):
        self.ready()
        self.ER |= code
        self.CS |= (1<<15) | (1<<14)
        if code == RK05.RKOVR:
            msg = "operation overflowed the disk"
        elif code == RK05.RKNXD:
            msg = "invalid disk accessed"
        elif code == RK05.RKNXC:
            msg = "invalid cylinder accessed"
        elif code == RK05.RKNXS:
            msg = "invalid sector accessed"
        self.system.panic(msg)

    def rwsec(self, write):
        '''Read/write entire sector (512 bytes) to/from memory'''
        if self.drive != 0: self.error(RK05.RKNXD)
        if self.cylinder > 0o312: self.error(RK05.RKNXC)
        if self.sector > 0o13: self.error(RK05.RKNXS)
        pos = (self.cylinder * 24 + self.surface * 12 + self.sector) * 512
        for i in range(0, 256):
            if not self.WC: break
            if write:
                # Words are 16-bit
                val = self.system.memory[self.BA >> 1]
                self.disk[pos] = val & 0xFF
                self.disk[pos+1] = (val >> 8) & 0xFF
            else:
                self.system.memory[self.BA >> 1] = self.disk[pos] | (self.disk[pos+1] << 8)
            self.BA += 2
            self.WC = (self.WC + 1) & 0xFFFF
            pos += 2

        # Check for overflow
        self.sector += 1
        if self.sector > 0o13:
            self.sector = 0
            self.surface += 1
            if self.surface > 1:
                self.surface = 0
                self.cylinder += 1
                if self.cylinder > 0o312:
                    self.error(RK05.RKOVR)

        if self.WC:
                #setTimeout('rkrwsec('+t+')', 3);
                #time.sleep(0.003)      # seems unnecessary
                self.rwsec(write)
        else:
                self.ready()
                if self.CS & (1<<6):
                     self.system.interrupt(Interrupt.RK, 5)

    def go(self):
        op = (self.CS & 0xF) >> 1
        if op == 0:
            self.system.writedebug('WARNING: resetting the drive via op == 0\n')
            self.reset()
        elif op == 1:
            self.notready()
            #setTimeout('rkrwsec(true)', 3)
            time.sleep(0.003)           # TODO: do we need it?
            self.rwsec(True)
        elif op == 2:
            self.notready()
            #setTimeout('rkrwsec(false)', 3)
            time.sleep(0.003)           # TODO: do we need it?
            self.rwsec(False)
        else:
            self.system.panic('unimplemented RK05 operation 0x{:x}'.format(op))

    def write16(self, a, v):
        if a in [0o777400, 0o777402]: return
        elif a == 0o777404:
            self.BA = (self.BA & 0xFFFF) | ((v & 0o60) << 12)
            v &= 0o17517       # writable bits
            self.CS &= ~0o17517
            self.CS |= v & ~1  # dont set GO bit
            if v & 1:
                self.go()
        elif a == 0o777406:
            self.WC = v
        elif a == 0o777410:
            self.BA = (self.BA & 0x30000) | v
        elif a == 0o777412:
            self.drive = v >> 13
            self.cylinder = (v >> 5) & 0o377
            self.surface = (v >> 4) & 1
            self.sector = v & 15
        else:
            self.system.panic('invalid write')

if __name__=='__main__':
    sys = System()
    rk05 = RK05(sys)

