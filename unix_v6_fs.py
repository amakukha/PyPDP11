#!/usr/bin/env python3

# Implementation of the Version 6 Unix filesystem in Python 3.
# Part of the PyPDP11 emulator project: 
#     https://github.com/amakukha/PyPDP11
# Copyright (c) 2019, Andriy Makukha, MIT Licence

import struct

BLOCK_SIZE = 512
INODE_SIZE = 32

class INode:
    def __init__(self, *args):
        if len(args)==20:
            self.setup(*args)
        elif len(args)==1:
            if type(args[0])!=bytes:
                # file assumed
                data = args[0].read(INODE_SIZE)
            else:
                data = args[0]
            params = struct.unpack('HBBBBHHHHHHHHHII', data)
            self.setup(*params)
        else:
            raise ValueError("wrong input")

    def setup(self, *args):
        # According to Unix V6 /usr/man/man5/fs.5
        self.flag = args[0]             # short
        self.nlinks = args[1]           # byte: number of links to file
        self.uid = args[2]              # byte: user ID of owner
        self.gid = args[3]              # byte: group ID of owner
        self.size = (args[4]<<16) + args[5]   # byte + short
        self.addr = args[6:14]          # uint16_t[8]: device addresses constituting file
        self.actime = args[14]          # time of last access
        self.modtime = args[15]         # time of last modification

    def is_dir(self):
        return bool(self.flag & 0x6000)

    def is_large(self):
        return bool(self.flag & 0x1000)

    def type(self):
        return (self.flag & 0x6000) >> 13

    def flags_string(self):
        '''Represent the flag word as a string'''
        s = ''
        s += 'a' if self.flag & 0x8000 else '.'
        fmt = (self.flag & 0x6000) >> 13
        s += {0: 'F', 1: 'S', 2: 'D', 3: 'B'}[fmt]
        s += 'L' if self.flag & 0x1000 else '.'
        s += 'U' if self.flag & 0x0800 else '.'
        s += 'G' if self.flag & 0x0400 else '.'
        s += 'R' if self.flag & 0x0100 else '.'
        s += 'W' if self.flag & 0x0080 else '.'
        s += 'X' if self.flag & 0x0040 else '.'
        s += 'R' if self.flag & 0x0020 else '.'
        s += 'W' if self.flag & 0x0010 else '.'
        s += 'X' if self.flag & 0x0008 else '.'
        s += 'R' if self.flag & 0x0004 else '.'
        s += 'W' if self.flag & 0x0002 else '.'
        s += 'X' if self.flag & 0x0001 else '.'
        return s

    def decode_flags(self):
        '''Represent some flags as a list'''
        flags = []
        if self.flag & 0x8000:
            flags.append('alloc')
        # type
        fmt = (self.flag & 0x6000) >> 13
        flags.append({0: 'file', 1: 'spec', 2: 'dir', 3: 'block'}[fmt])
        if self.flag & 0x1000:
            flags.append('large')
        return flags

    def __repr__(self):
        return 'INode(uid={uid},gid={gid},addrs={addr},size={size},flags={flags})'.format(
                    uid=self.uid, gid=self.gid, addr=str(self.addr), size=self.size,
                    flags=str(self.decode_flags()),
                )

class UnixV6FileSystem:
    def __init__(self, filename):
        self.f = open(filename, 'rb')

    def read_i_node(self, i):
        self.f.seek(BLOCK_SIZE*2 + (i-1)*32)
        node = INode(self.f)
        return node

    def ensure_i_node(self, x):
        if isinstance(x, INode):
            return x
        return self.read_i_node(x)

    def read_flags(self, x):
        inode = self.ensure_i_node(x)
        return inode.flags_string()

    def read_block(self, b):
        self.f.seek(BLOCK_SIZE*b)
        data = self.f.read(BLOCK_SIZE)
        return data

    def read_file(self, *args):
        inode = self.ensure_i_node(args[0])
        if inode.size > BLOCK_SIZE*BLOCK_SIZE/2*8:
            raise ValueError('huge files not implemented')
        contents = b''
        if not inode.is_large():
            for n in inode.addr:
                if n == 0: break
                contents += self.read_block(n)
        else:
            for blk in inode.addr:
                indirect_block = self.read_block(blk)
                for i in range(0, len(indirect_block), 2):
                    n = struct.unpack('H', indirect_block[i:i+2])[0]
                    if n == 0: break
                    contents += self.read_block(n)
                if n == 0: break
        contents = contents[:inode.size]
        return contents

    def sum_file(self, *args):
        '''
        This computes the same file checksum as Unix V6's `sum` utility.

        The algorithm of the checksum was explained by user `palupicu`:
            https://unix.stackexchange.com/a/526658/274235
        '''
        if type(args[0])==bytes:
            data = args[0]
        else:
            data = self.read_file(*args)
        s = 0
        for i in range(len(data)):
            c = struct.unpack('B', data[i:i+1])[0]
            s += c if c <= 0x7F else (c | 0xFF00)
            if s>0xFFFF:    # 16-bit overflow
                s = (s+1) & 0xFFFF
        return s

    def list_dir(self, *args):
        inode = self.ensure_i_node(args[0])
        # Read & interpret file
        if not inode.is_dir():
            return None
        files = []
        data = self.read_file(inode)
        for i in range(0, len(data), 16):
            inum, name = struct.unpack('H14s', data[i:i+16])
            if inum > 0:
                name = name.decode().rstrip('\x00')
                files.append((inum, name))
        return files

    def tree(self, inum, tabs=0):
        '''Prints subdirectory tree to standard output.
        Shows all the files, together with flags, size and checksum.
        Call it like `fs.tree(1)` to descend into the root directory (first inode).
        Returns size of all files, as well as number of occupied blocks.
        '''
        dir_node = fs.read_i_node(inum)
        data = fs.list_dir(dir_node)
        if data is None:
            return
        data.sort(key = lambda x: x[1])
        last_inum, last_name = 0, ''
        size, blk_size = 0, 0
        for inum, name in data:
            if (last_inum, last_name) == (inum, name):
                continue
            print(' '*tabs,end='')
            node = self.read_i_node(inum)
            contents = self.read_file(inum)
            print('{name:15s}\t{size}\t{flags}\tsum={sum}'.format(
                        name = name + ('/' if node.is_dir() else ' '),
                        flags = node.flags_string(),
                        size = node.size,
                        sum = self.sum_file(contents))
            )
            size += node.size
            blk_size += (node.size // 512) + (1 if node.size % 512 else 0)
            if name not in '..' and node.is_dir():
                # Recursion into subdirectories
                sz, blk_sz = self.tree(inum, tabs + 4)
                size += sz
                blk_size += blk_sz
            last_inum, last_name = inum, name
        return size, blk_size

if __name__=='__main__':
    fs = UnixV6FileSystem('rk0.img')
    size, blk_size = fs.tree(1)     # prints entire filesystem tree
    print('Total size: %d, Block size: %d (%d)' % (size, blk_size*BLOCK_SIZE, blk_size))
    #print(fs.sum_file(bytes(('1111111111\n'*320).encode())))       # should return 28930 (same as SYSV checksum for text files)
