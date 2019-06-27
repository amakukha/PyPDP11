#!/usr/bin/env python3

# Implementation of the Version 6 Unix filesystem in Python 3.
# Part of the PyPDP11 emulator project: 
#     https://github.com/amakukha/PyPDP11
# Copyright (c) 2019, Andriy Makukha, MIT Licence

import struct, os, array, time

SUPERBLOCK_SIZE = 415
BLOCK_SIZE = 512
INODE_SIZE = 32
BIGGEST_NOT_HUGE_SIZE = BLOCK_SIZE*BLOCK_SIZE/2*8

# TODO:
# - check that all the free nodes in the chain are actually used 
# - check that all the allocated nodes (files) belong to some parent directory

class HugeFileError(ValueError):
    pass

class Superblock:
    def __init__(self, *args):
        if type(args[0])!=bytes:
            data = args[0].read(SUPERBLOCK_SIZE)
        else:
            data = args[0]
        self.parse(data)

    def parse(self, data):
        self.isize, self.fsize, self.nfree = struct.unpack('HHH', data[:6])
        self.free = array.array('H', data[6:206])
        self.ninode = struct.unpack('H', data[206:208])[0]
        self.inode = array.array('H', data[208:408])
        self.flock, self.ilock, self.fmod = struct.unpack('BBB', data[408:411])
        self.time = struct.unpack('I', data[411:415])[0]

    def serialize(self):
        data  = struct.pack('HHH', self.isize, self.fsize, self.nfree)
        data += self.free.tobytes()
        data += struct.pack('H', self.ninode)
        data += self.inode.tobytes()
        data += struct.pack('BBB', self.flock, self.ilock, self.fmod)
        data += struct.pack('I', self.time)
        return data

    def __repr__(self):
        return 'Superblock(isize={isize},fsize={fsize},nfree={nfree},ninode={ninode})'.format(
                    isize=self.isize, fsize=self.fsize, nfree=self.nfree, ninode=self.ninode
                )

class INode:
    def __init__(self, *args):
        self.inode = 0
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
            self.setup(*([0]*16))
            #self.actime = self.modtime = int(time.time())
            self.actime = self.modtime = 0xa60012ce         # 01 Jan 1980, 00:00:00
            self.flag = 0x8000 | 0x01FF         # allocated file, everything is allowed
            self.nlinks = 1

    def setup(self, *args):
        # According to Unix V6 /usr/man/man5/fs.5
        self.flag = args[0]             # short
        self.nlinks = args[1]           # byte: number of links to file
        self.uid = args[2]              # byte: user ID of owner
        self.gid = args[3]              # byte: group ID of owner
        self.size = (args[4]<<16) + args[5]   # byte + short
        self.addr = list(args[6:14])    # uint16_t[8]: device addresses constituting file
        self.actime = args[14]          # time of last access
        self.modtime = args[15]         # time of last modification

    def serialize(self):
        data = struct.pack('HBBBBH', self.flag, self.nlinks, self.uid, self.gid, self.size>>16, self.size & 0xFFFF)
        for i in range(8):
            data += struct.pack('H', self.addr[i])
        data += struct.pack('II', self.actime, self.modtime)
        return data

    def set_free(self):                 # disallocate, mark inode as free
        self.flag &= 0x7FFF

    def set_directory(self):
        self.flag |= 0x4000

    def set_large(self):
        self.flag |= 0x1000

    def clear_large(self):
        self.flag &= 0xEFFF
        
    def is_allocated(self):
        return bool(self.flag & 0x8000)

    def is_dir(self):
        return bool((self.flag & 0x4000) == 0x4000)

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

    def __repr__(self):
        return 'INode(uid={uid},gid={gid},addrs={addr},size={size},flags={flags})'.format(
                    uid=self.uid, gid=self.gid, addr=str(self.addr), size=self.size,
                    flags=self.flags_string(),
                )

class UnixV6FileSystem:
    def __init__(self, filename):
        self.f = open(filename, 'r+b')

    def read_superblock(self):
        self.f.seek(BLOCK_SIZE)
        sup = Superblock(self.f)
        return sup

    def write_block(self, blkn, data):
        if len(data) > BLOCK_SIZE:
            raise ValueError('data is too big to fit into one block')
        data += b'\x00' * (BLOCK_SIZE - len(data)) 
        self.f.seek(BLOCK_SIZE*blkn)
        self.f.write(data)

    def write_superblock(self, sup):
        data = sup.serialize()
        self.write_block(1, data)

    def read_i_node(self, i):
        self.f.seek(BLOCK_SIZE*2 + (i-1)*32)
        node = INode(self.f)
        node.inode = i          # remember its number for convenience
        return node

    def write_i_node(self, node):
        data = node.serialize()
        self.f.seek(BLOCK_SIZE*2 + (node.inode-1)*32)
        self.f.write(data)

    def ensure_i_node(self, x):
        if isinstance(x, INode):
            return x
        return self.read_i_node(x)

    def read_flags(self, x):
        inode = self.ensure_i_node(x)
        return inode.flags_string()

    def read_block(self, blkn):
        self.f.seek(BLOCK_SIZE*blkn)
        data = self.f.read(BLOCK_SIZE)
        return data

    def read_file(self, *args):
        inode = self.ensure_i_node(args[0])
        if inode.size > BIGGEST_NOT_HUGE_SIZE:
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
        for c in data:
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

    def find_i_node(self, path, node=1):
        if path and path[0]=='/':
            return self.find_i_node(path.strip('/'))       # root directory, we already know the inode (1)
        #print(path, node)
        inode = self.read_i_node(node)
        if not path:
            if inode.is_allocated():
                inode.inode = node
                return inode
            return None
        if inode.is_dir(): 
            name, tail = path.split('/', 1) if '/' in path else (path, '')
            for no, nm in self.list_dir(inode):
                if nm != name: continue
                return self.find_i_node(tail, no)
        return None

    def tree(self, inum, save_path=None, tabs=0):
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
            if not node.is_dir() and save_path is not None:
                filepath = os.path.join(save_path, name)
                open(filepath, 'wb').write(contents)
            print('{name:15s}\t{size}\t{flags}\tsum={sum}\t{nlinks:d}'.format(
                        name = name + ('/' if node.is_dir() else ' '),
                        flags = node.flags_string(),
                        size = node.size,
                        sum = self.sum_file(contents),
                        nlinks = node.nlinks)
            )
            size += node.size
            blk_size += (node.size // 512) + (1 if node.size % 512 else 0)
            if name not in '..' and node.is_dir():
                # Recursion into subdirectories
                if save_path is None:
                    sz, blk_sz = self.tree(inum, None, tabs + 4)
                else:
                    dirpath = os.path.join(save_path, name)
                    os.mkdir(dirpath)
                    sz, blk_sz = self.tree(inum, dirpath, tabs + 4)
                size += sz
                blk_size += blk_sz
            last_inum, last_name = inum, name
        return size, blk_size

    def extract(self, dirname):
        '''Create a directory and extract all the files from the disk image'''
        if os.path.exists(dirname):
            raise ValueError("folder exists")
        os.mkdir(dirname)
        return self.tree(1, dirname)

    def path_exists(self, path):
        return self.find_i_node(path) is not None

    def allocate_i_node(self):
        '''This function return the number of inode'''
        sup = self.read_superblock()
        if sup.ninode <= 0:
            sup.ninode = 0
            # Find free inodes
            for i in range(1, sup.isize*BLOCK_SIZE//INODE_SIZE+1):
                node = self.read_i_node(i)
                if not node.is_allocated():
                    sup.inode[sup.ninode] = i
                    sup.ninode += 1
        if sup.ninode > 0:
            sup.ninode -= 1
            inode = sup.inode[sup.ninode]
            self.write_superblock(sup)
            # Create new node object (allocated/file)
            node = INode()
            node.inode = inode
            return node
        else:
            raise Exception("no free inodes")

    def free_i_node(self, inode):
        sup = self.read_superblock()
        if sup.ninode<100:
            sup.inode[sup.ninode] = inode
            sup.ninode += 1
            self.write_superblock(sup)
        # "the information as to whether the inode is really free or not is maintained in the inode itself"
        node = self.ensure_i_node(inode)
        node.set_free()
        selr.write_i_node(node)

    def allocate_block(self):
        # Returns block number
        sup = self.read_superblock()
        sup.nfree -= 1
        blkn = sup.free[sup.nfree]
        if sup.nfree>0:
            self.write_superblock(sup)
            if blkn == 0:
                raise ValueError('allocated free block number is zero')
            return blkn
        # Retrieve block from the chain
        blk = self.read_block(blkn)
        sup.nfree = struct.unpack('H', blk[:2])[0]
        for i in range(100):
            sup.free[i] = struct.unpack('H', blk[2+2*i:4+2*i])[0]
        self.write_superblock(sup)
        return blkn

    def free_block(self, blkn):
        sup = self.read_superblock()
        if sup.nfree >= 100:
            data = struct.pack('H', sup.nfree)
            for i in range(100):
                data += struct.pack('H', sup.free[i])
            self.write_block(blkn, data)
            sup.nfree = 0
        sup.free[sup.nfree] = blkn
        sup.nfree += 1
        self.write_superblock(sup)
            

    def mkdir(self, dst):
        # Check correctness
        node = self.find_i_node(dst)
        if node:
            raise ValueError("destination exists")
        # Find parent directory
        dirpath, name = os.path.split(dst)
        print ('DIRPATH:',dirpath)
        pnode = self.find_i_node(dirpath)
        if not pnode:
            raise ValueError("destination parent not found")

        # Allocate inode & block (new directory - always one block)
        node = fs.allocate_i_node()
        block = fs.allocate_block()
        
        # Write block
        data  = struct.pack('H', node.inode)
        data += b'.' + b'\x00'*13
        data += struct.pack('H', pnode.inode)
        data += b'..' + b'\x00'*12
        self.write_block(block, data)

        # Write inode
        node.set_directory()
        node.addr[0] = block
        node.size = 32
        self.write_i_node(node)
        print(node)

        # Add directory inode to parent directory
        self.add_to_directory(pnode, node, name)

    def add_to_directory(self, dnode, fnode, name):
        dnode = self.ensure_i_node(dnode)
        if dnode.is_large() or dnode.size+16 >= BLOCK_SIZE*8:
            raise ValueError("writing to large directories is not supported")

        # Read last/new block
        i = dnode.size // BLOCK_SIZE
        if dnode.size % BLOCK_SIZE == 0:
            # Previous directory blocks are full, allocate new one
            dnode.addr[i] = self.allocate_block()
        blksz = dnode.size - BLOCK_SIZE*i
        block = self.read_block(dnode.addr[i])[:blksz]
        
        # Add record to directory blocks
        block += struct.pack('H', fnode.inode)
        name = name[:14]
        block += name.encode() + b'\x00'*(14-len(name))
        self.write_block(dnode.addr[i], block)

        # Update directory size
        dnode.size += 16
        self.write_i_node(dnode)

    def upload_file(self, src, dst):
        fnode = self.find_i_node(dst)      # inode of the file to be overwritten
        pnode = None                       # inode of the directory to be written into
        dstname = None                     # destination base filename
        if fnode is not None:
            if fnode.is_dir():
                pnode = fnode
                fnode = None
                dirpath = dst
                dstname = os.path.split(src)[1]
            else:
                print('Overwriting file:', dst)
        if dstname is None:
            dstname = os.path.split(dst)[1]

        # Find parent directory 
        if pnode is None:
            dirpath = os.path.split(dst)[0]
            pnode = self.find_i_node(dirpath)
            if pnode is None:
                raise ValueError("destination directory not found")
            elif not pnode.is_dir():
                raise ValueError("destination path incorrect")
        print('Writing into directory:', dirpath)

        # Retrieve file from the local filesystem
        if not os.path.exists(src):
            raise ValueError("file {} doesn't exist".format(src))
        contents = open(src,'rb').read()
        size = len(contents)

        # Allocate inode if not overwriting
        if fnode is None:
            fnode = self._create_file(contents)
            self.add_to_directory(pnode, fnode, dstname)
        else:
            self.overwrite_file(fnode, contents)

    def _create_file(self, contents):
        fnode = self.allocate_i_node()
        try:
            self.overwrite_file(fnode, contents)
            print('File created:', fnode)
            return fnode
        except HugeFileError as e:
            self.free_i_node(fnode)
            raise e

    def overwrite_file(self, fnode, contents):
        if len(contents) > BIGGEST_NOT_HUGE_SIZE:
            raise HugeFileError("creating huge files not supported")
        fnode.size = len(contents)
        fnode.addr = [0]*8
        
        # Allocate and write blocks
        last_block = (fnode.size-1)//BLOCK_SIZE
        if len(contents) <= BLOCK_SIZE*8:
            # Small file
            fnode.clear_large()
            for i in range(last_block+1):
                blkn = self.allocate_block()
                fnode.addr[i] = blkn
                if i!=last_block:
                    self.write_block(blkn, contents[i*BLOCK_SIZE:(i+1)*BLOCK_SIZE])
                else:
                    self.write_block(blkn, contents[i*BLOCK_SIZE:])
        else:
            # Large file (but not huge)
            fnode.set_large()
            blkcnt = 0
            for a in range(8):
                ablkn = self.allocate_block()
                ablkdata = b''
                fnode.addr[a] = ablkn
                for b in range(256):
                    blkn = self.allocate_block()
                    ablkdata += struct.pack('H', blkn)
                    if blkcnt!=last_block:
                        self.write_block(blkn, contents[blkcnt*BLOCK_SIZE:(blkcnt+1)*BLOCK_SIZE])
                    else:
                        self.write_block(blkn, contents[blkcnt*BLOCK_SIZE:])
                        break
                    blkcnt += 1
                self.write_block(ablkn, ablkdata)
                if blkcnt==last_block:
                    break

        # Write inode
        self.write_i_node(fnode)

    def test(self):
        def local_print(test, res):
            print('{:>30}: {}'.format(test, 'OK' if res else 'FAILED'))

        # Test 1
        supdata0 = self.read_block(1)
        sup = self.read_superblock()
        local_print('SUPERBLOCK SERIALIZATION', supdata0[:SUPERBLOCK_SIZE] == sup.serialize()) 

        # Test 2
        blkn = self.allocate_block()
        self.free_block(blkn)
        sup = self.read_superblock()
        local_print('ALLOCATE/FREE BLOCK', supdata0 == self.read_block(1)) 

        # Test 3
        found = self.path_exists('/usr/sys/dmr/hp.c')
        local_print('FOUND PATH', found)

if __name__=='__main__':
    fs = UnixV6FileSystem('rk0.img')
    fs.test()

    from sys import argv
    if argv[1] in ['tree', 'extract']:
        if argv[1] == 'tree':
            # Command "tree" prints entire filesystem tree
            size, blk_size = fs.tree(1)
        else:
            # Command "extract" - extracts all the files into new directory
            size, blk_size = fs.extract(argv[2])   
        print('Total size: %d, Block size: %d (%d)' % (size, blk_size*BLOCK_SIZE, blk_size))
    
    elif argv[1] == 'mkdir':
        # Command "mkdir" - make new directory
        fs.mkdir(argv[2])

    elif argv[1] == 'exists':
        # Command "exists" - check if file/directory exists
        print(fs.path_exists(argv[2]))

    elif argv[1] == 'upload':
        # Command 'umpoad' - copy file from local filesystem into Unix V6 filesystem
        fs.upload_file(argv[2], argv[3])

    elif argv[1] == 'sum':
        # Command 'sum' - Unix V5 checksum local file 
        print(fs.sum_file(open(argv[2], 'rb').read()))

