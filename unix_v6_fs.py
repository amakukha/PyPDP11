#!/usr/bin/env python3

# Implementation of the Version 6 Unix filesystem in Python 3.
# Part of the PyPDP11 emulator project: 
#     https://github.com/amakukha/PyPDP11
# Copyright (c) 2019, Andriy Makukha, MIT Licence

import struct, os, array, time, datetime, io, string, threading, base64

DISK_IMAGE_FILENAME = 'rk0.img'

SUPERBLOCK_SIZE = 415
BLOCK_SIZE = 512
INODE_SIZE = 32
BIGGEST_NOT_HUGE_SIZE = BLOCK_SIZE*BLOCK_SIZE/2*8

# Higher bytes of file modtime used by PyPDP11 for syncing and creating
CREATED_BY_PYPDP11 = 0x13000000         # all in 1980
SYNCED_BY_PYPDP11  = 0x15000000         # all in 1981

TMP_FILENAME = 'tmp.b64'
TIME_DELTA = 60
TIME_ERROR_S = 47                       # it's unclear why the difference appears to be 47 on my machine TODO

# TODO:
# - check that all the non-free nodes (according to the chain) are actually used 
# - check that all the allocated nodes (files) belong to some parent directory

class HugeFileError(ValueError):
    pass

class SyncError(ValueError):
    pass

class Superblock:
    def __init__(self, *args):
        if type(args[0])!=bytes:
            data = args[0].read(SUPERBLOCK_SIZE)
        else:
            data = args[0]
        self.parse(data)

    def parse(self, data):
        # According to Unix V6 /usr/man/man5/fs.5
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
        if len(args)==18:
            self.setup(*args)
        elif len(args)==1:
            if type(args[0])!=bytes:
                # file assumed
                data = args[0].read(INODE_SIZE)
            else:
                data = args[0]
            params = struct.unpack('HBBBBHHHHHHHHHHHHH', data)
            self.setup(*params)
        else:
            self.setup(*([0]*18))
            tt = int(time.time())               # current Unix epoch time
            self.actime = self.modtime = CREATED_BY_PYPDP11 | (tt & 0xFFFFFF)
            self.flag = 0x8000 | 0x01FF         # allocated file, all the permissions granted
            self.nlinks = 1                     # TODO: how to set these properly?

    def setup(self, *args):
        # According to Unix V6 /usr/man/man5/fs.5
        self.flag = args[0]             # short
        self.nlinks = args[1]           # byte: number of links to file
        self.uid = args[2]              # byte: user ID of owner
        self.gid = args[3]              # byte: group ID of owner
        self.size = (args[4]<<16) + args[5]   # byte + short
        self.addr = list(args[6:14])    # uint16_t[8]: device addresses constituting file
        self.actime = (args[14] << 16) | args[15]  # time of last access 
        self.modtime = (args[16] << 16) | args[17] # time of last modification

    def serialize(self):
        data = struct.pack('HBBBBH', self.flag, self.nlinks, self.uid, self.gid, self.size>>16, self.size & 0xFFFF)
        for i in range(8):
            data += struct.pack('H', self.addr[i])
        data += struct.pack('HHHH', self.actime >> 16, self.actime & 0xFFFF, self.modtime >> 16, self.modtime & 0xFFFF)
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

    def is_regular_file(self):
        return bool((self.flag & 0x4000) == 0x0000)

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

    def __lt__(self, other):
        return self.inode < other.inode

    def __repr__(self):
        return 'INode(uid={uid},gid={gid},addrs={addr},size={size},flags={flags})'.format(
                    uid=self.uid, gid=self.gid, addr=str(self.addr), size=self.size,
                    flags=self.flags_string(),
                )

class UnixV6FileSystem:
    def __init__(self, arg: str or bytes):
        if isinstance(arg, str):
            # Filename assumed
            self.f = open(arg, 'r+b')
        elif isinstance(arg, bytes):
            # Actual data assumed
            self.f = io.BytesIO(arg)

    def read_superblock(self):
        self.f.seek(BLOCK_SIZE)
        sup = Superblock(self.f)
        return sup

    def write_block(self, blkn: int, data: bytes):
        if len(data) > BLOCK_SIZE:
            raise ValueError('data is too big to fit into one block')
        data += b'\x00' * (BLOCK_SIZE - len(data)) 
        self.f.seek(BLOCK_SIZE*blkn)
        self.f.write(data)

    def write_superblock(self, sup: Superblock):
        data = sup.serialize()
        self.write_block(1, data)

    def read_i_node(self, i: int):
        self.f.seek(BLOCK_SIZE*2 + (i-1)*32)
        node = INode(self.f)
        node.inode = i          # remember its number for convenience
        return node

    def write_i_node(self, node: INode):
        data = node.serialize()
        self.f.seek(BLOCK_SIZE*2 + (node.inode-1)*32)
        self.f.write(data)

    def ensure_i_node(self, x: INode or int):
        if isinstance(x, INode):
            return x
        return self.read_i_node(x)

    def read_flags(self, x: INode or int):
        inode = self.ensure_i_node(x)
        return inode.flags_string()

    def read_block(self, blkn: int):
        self.f.seek(BLOCK_SIZE*blkn)
        data = self.f.read(BLOCK_SIZE)
        return data

    def yield_node_blocks(self, node: INode or int, include_all=False) -> int:
        node = self.ensure_i_node(node)
        if node.size > BIGGEST_NOT_HUGE_SIZE:
            raise HugeFileError('huge files not implemented')
        if not node.is_large():
            for n in node.addr:
                if n == 0: return
                yield n
        else:
            for blk in node.addr:
                if not blk: return
                if include_all:
                    yield blk
                indirect_block = self.read_block(blk)
                for i in range(0, len(indirect_block), 2):
                    n = struct.unpack('H', indirect_block[i:i+2])[0]
                    if n == 0: return
                    yield n

    def read_file(self, node: INode or int):
        node = self.ensure_i_node(node)
        contents = b''
        for n in self.yield_node_blocks(node):
            contents += self.read_block(n)
        return contents[:node.size]
        
    def sum_file(self, x: bytes or INode or int):
        '''
        This computes the same file checksum as Unix V6's `sum` utility.

        The algorithm of the checksum was explained by user `palupicu`:
            https://unix.stackexchange.com/a/526658/274235
        '''
        if isinstance(x, bytes):
            data = x
        else:
            data = self.read_file(x)
        s = 0
        for c in data:
            s += c if c <= 0x7F else (c | 0xFF00)
            if s>0xFFFF:    # 16-bit overflow
                s = (s+1) & 0xFFFF
        return s

    def list_dir(self, dnode: INode or int) -> [(int, str)]:
        inode = self.ensure_i_node(dnode)
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

    def path_i_node(self, path, node=1):
        if path and path[0]=='/':
            return self.path_i_node(path.strip('/'))       # root directory, we already know the inode (1)
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
                return self.path_i_node(tail, no)
        return None
    
    def start_sync_thread(self, unix_dir: 'path', local_dir: 'path', terminal):
        self._unix_dir = unix_dir
        self._local_dir = local_dir
        self._terminal = terminal

        self.sync_running = threading.Event()
        self.sync_finished = threading.Event()
        self.sync_finished.clear()

        self.sync_thread = threading.Thread(target=self.sync_method)
        self.sync_thread.daemon = True
        self.sync_thread.start()

    def sync_method(self):
        '''The purpose of this thread is to execute complete syncing.
        This needs to be done in a separate thread because syncing into live Unix V6 needs to emulate user.
        Therefore this thread sends commands to Unix, while keeping the CPU ang GUI threads running.
        '''
        self.sync(self._unix_dir, self._local_dir, self._terminal)
        self.sync_finished.set()

    def sync_prompt(self, last_printed):
        self.sync_running.set()

    @staticmethod
    def synctime(local_fn):
        '''Get modtime of a local file. If modtime is not divisible by 60, truncate to minute.'''
        lmtime = int(os.stat(local_fn).st_mtime)
        if lmtime % 60:
            latime = int(os.stat(local_fn).st_atime)
            lmtime = lmtime - lmtime % 60
            os.utime(local_fn, (latime, lmtime))
        return SYNCED_BY_PYPDP11 | (0xFFFFFF & lmtime)

    def sync(self, unix_dir: 'path', local_dir: 'path', terminal=None, root=True):
        '''Synchronizes Unix V6 directory with a local directory.
        The algorithm uses file modification timestamps for tracking changes.
        The highest byte of the timestamp is set to either 0x13 (CREATED) or 0x15 (SYNCED) by this script.
        The assumption is that if the highest byte is not one of those two, the file was created by or
        modified by Unix V6. A file modified by Unix is always downloaded to a local directory and its 
        highest byte is set to SYNCED. Otherwise, the file in Unix V6 can be overwritten if local directory
        contains a newer version (that is, different from already uploaded).

        Downloading a file accesses it directly in Unix V6 filesystem. Uploading a file either puts it
        directly into filesystem if Unix was not loaded yet or takes over the terminal and executes
        necessary commands to create identical file through the operating system.

        Based on my directories comparing script: 
            https://gist.github.com/amakukha/f489cbde2afd32817f8e866cf4abe779
        '''
        # Ensure validity
        dnode = self.path_i_node(unix_dir)
        if dnode is None:
            raise SyncError('"{}" not found in filesystem'.format(unix_dir))
        if not dnode.is_dir():
            raise ValueError('"{}" is not Unix V6 directory'.format(unix_dir))
        if not os.path.exists(local_dir):
            print('Creating:', local_dir)
            os.mkdir(local_dir)
        elif not os.path.isdir(local_dir):
            raise SyncError('local directory "{}" not found'.format(local_dir))

        # Get lists of files
        ufs = [(fn, os.path.join(unix_dir, fn), self.read_i_node(inum)) for inum, fn in self.list_dir(dnode)]
        lfs = [(fn, os.path.join(local_dir, fn)) for fn in os.listdir(local_dir)]

        # Determine type
        ufs = sorted([(fn, pth, node.is_dir(), node) for fn, pth, node in ufs if fn[0]!='.'])
        lfs = sorted([(fn, pth, os.path.isdir(pth)) for fn, pth in lfs if fn[0]!='.'])

        # Synchronize current dirrectory

        def show_message(msg):
            if terminal is None:
                print(msg)
            else:
                terminal.writedebug(msg + '\n')

        via_terminal = False
        def download(uitem, ldir):
            show_message('DOWNLOAD: {} into {}'.format(uitem[1], local_dir))
            local_fn = os.path.join(local_dir, uitem[0])
            self.download_file(uitem[3], local_fn)
            # Set the synced flags
            if terminal is None or terminal.prompt_cnt == 0:
                uitem[3].modtime = self.synctime(local_fn)
                self.write_i_node(uitem[3])
            else:
                via_terminal = True
                self.mark_synced_via_terminal(local_fn, uitem[1], terminal)

        def upload(litem, udir):
            nonlocal via_terminal
            show_message('UPLOAD: {} into {}'.format(litem[1], unix_dir))
            dst_fn = os.path.join(unix_dir, litem[0])
            if terminal is None or terminal.prompt_cnt == 0:
                node = self.upload_file(litem[1], dst_fn)
                # Set the local time
                node.modtime = self.synctime(litem[1])
                self.write_i_node(node)
            else:
                via_terminal = True
                self.upload_via_terminal(litem[1], dst_fn, terminal)

        ui = li = cnt = 0
        sync_subdirs = []
        while ui < len(ufs) and li < len(lfs):
            if ufs[ui][0] == lfs[li][0]:        # same name
                if ufs[ui][2] == lfs[li][2]:    # same type
                    if ufs[ui][2]:
                        sync_subdirs.append((ufs[ui][1], lfs[li][1]))
                    else:
                        # COMPARE FILES
                        umtime = ufs[ui][3].modtime
                        lmtime = int(os.stat(lfs[li][1]).st_mtime)
                        if (umtime & 0xFF000000) not in [CREATED_BY_PYPDP11, SYNCED_BY_PYPDP11]:
                            download(ufs[ui], local_dir)
                        elif abs((umtime & 0xFFFFFF) - (lmtime & 0xFFFFFF) + TIME_ERROR_S)>TIME_DELTA:
                            print('Time difference {}'.format((umtime & 0xFFFFFF) - (lmtime & 0xFFFFFF)))
                            upload(lfs[li], unix_dir)
                else:
                    raise SyncError('type mismatch: {} and {}'.format(ufs[ui][1], lfs[li][1]))
                ui += 1;  li += 1
            elif ufs[ui][0] < lfs[li][0]:
                if ufs[ui][2]:
                    sync_subdirs.append((ufs[ui][1], os.path.join(local_dir, ufs[ui][0])))
                else:
                    download(ufs[ui], local_dir)
                ui += 1
            else:
                if lfs[li][2]:
                    sync_subdirs.append((os.path.join(unix_dir, lfs[li][0]), lfs[li][1]))
                else:
                    upload(lfs[li], unix_dir) 
                li += 1
            cnt += 1

        # TODO: repeating code, DRY it
        while ui < len(ufs):
            if ufs[ui][2]:
                sync_subdirs.append((ufs[ui][1], os.path.join(local_dir, ufs[ui][0])))
            else:
                download(ufs[ui], local_dir)
            ui += 1
            cnt += 1
        while li < len(lfs):
            if lfs[li][2]:
                sync_subdirs.append((os.path.join(unix_dir, lfs[li][0]), lfs[li][1]))
            else:
                upload(lfs[li], unix_dir)
            li += 1
            cnt += 1

        # Sync subfolders recursively
        for udir, ldir in sync_subdirs:
            cnt, via_comm = self.sync(udir, ldir, terminal, root=False)
            via_terminal = via_terminal or via_comm

        if root and terminal:
            if via_terminal:
                self.command_wait('rm "{}" 2>/dev/null'.format(TMP_FILENAME), terminal)
                self.command_wait('sync', terminal)
            # sync finished @ FS

        return cnt if root else (cnt, via_terminal)

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
            print('{name:15s}\t{size}\t{flags}\tsum={sum}\t{nlinks:d}\t{modtime:x}'.format(
                        name = name + ('/' if node.is_dir() else ' '),
                        flags = node.flags_string(),
                        size = node.size,
                        sum = self.sum_file(contents),
                        nlinks = node.nlinks,
                        modtime = node.modtime)
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

    def extract_dir(self, dst_dirname, src_dirname='/'):
        '''Create a directory and extract all the files from the disk image'''
        if os.path.exists(dst_dirname):
            raise ValueError("folder exists")
        node = self.path_i_node(src_dirname) 
        os.mkdir(dst_dirname)
        return self.tree(node.inode, dst_dirname)

    def path_exists(self, path):
        return self.path_i_node(path) is not None

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
        node = self.path_i_node(dst)
        if node:
            raise ValueError("destination exists")
        # Find parent directory
        dirpath, name = os.path.split(dst)
        print ('DIRPATH:',dirpath)
        pnode = self.path_i_node(dirpath)
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

    def download_file(self, node: INode or int, dst: str):
        # TODO: allow accepting unix path
        # TODO: allow accepting directory as a destination
        node = self.ensure_i_node(node)
        data = self.read_file(node)
        open(dst, 'wb').write(data)

    def command_wait(self, command: str, terminal):
        '''Send command to terminal and wait for prompt'''
        self.sync_running.clear()
        terminal.queue_command(command, self.sync_prompt)
        self.sync_running.wait()

    def mark_synced_via_terminal(self, local_fn: 'path', unix_fn: 'path', terminal):
        '''Syncs modtime of a Unix file to indicate that it is synced with a local file'''
        modtime = self.synctime(local_fn) 
        tz_offset = 18000
        date = datetime.datetime.utcfromtimestamp(modtime-tz_offset).strftime('%m%d%H%M%y')
        self.command_wait('date {}'.format(date), terminal)
        
        # Touch to set modtime (or to create at the same time)
        self.command_wait('touch "{}"'.format(unix_fn), terminal)

    def upload_via_terminal(self, src: str, dst: str, terminal):
        # Retrieve file from the local filesystem
        if not os.path.exists(src):
            raise ValueError("file {} doesn't exist".format(src))

        # Determine if file can be echoed
        text_file = True
        contents = open(src,'rb').read()
        lines = contents.split(b'\n')
        allowed_characters = string.ascii_letters + string.digits + ' .,;:"\'`+-*/%=!?~$^&|\\()[]{}<>\n'
        max_len = 255 - len(" echo \"\" >> \n" + dst)
        if not (contents[-1:]==b'\n' and \
                max(len(x) for x in lines) <= max_len and \
                not [x for x in lines if b"'" in x and b'"' in x] and \
                set(contents).issubset(set(allowed_characters.encode()))):
            # Dump the file
            text_file = False
            contents = base64.standard_b64encode(contents)
            lines = [contents[i:i+64] for i in range(0, len(contents), 64)]
        else:
            lines = lines[:-1]      # drop the last empty line

        # Input via echo command
        first = True
        for line in lines:
            self.command_wait("echo {q}{line}{q} {a} {fn}".format(
                q = "'" if b'"' in line else '"',
                line = line.decode(),
                a = ' >' if first else '>>',
                fn = TMP_FILENAME if not text_file else dst
            ), terminal)
            first = False

        # Decode if needed
        if not text_file and lines:
            self.command_wait('base64 -D -i "{}" -o "{}"'.format(TMP_FILENAME, dst), terminal)

        # Mark file as synced (or create at the same time)
        self.mark_synced_via_terminal(src, dst, terminal)

        return self.path_i_node(dst)

    def upload_file(self, src: str, dst: str):
        fnode = self.path_i_node(dst)      # inode of the file to be overwritten
        pnode = None                       # inode of the directory to be written into
        dstname = None                     # destination base filename
        if fnode is not None:
            if fnode.is_dir():
                pnode = fnode
                fnode = None
                dirpath = dst
                dstname = os.path.split(src)[1]
                fnode = self.path_i_node(os.path.join(dirpath, dstname))
                if fnode:
                    print('Overwriting file:', os.path.join(dirpath, dstname))
            else:
                print('Overwriting:', dst)
        if dstname is None:
            dstname = os.path.split(dst)[1]

        # Find parent directory 
        if pnode is None:
            dirpath = os.path.split(dst)[0]
            pnode = self.path_i_node(dirpath)
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
        return fnode

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

        # Free all the occupied blocks
        if fnode.size > 0:
            for blkn in self.yield_node_blocks(fnode,include_all=True):
                self.free_block(blkn)

        # New size
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

    def get_free_blocks(self):
        '''Return list of all free block numbers'''
        sup = self.read_superblock()
        free = sup.nfree
        free_blks = []
        for blkn in sup.free[:sup.nfree]:
            if blkn:
                if blkn in free_blks:
                    print('error: 0 block {} repeated'.format(blkn))
                free_blks.append(blkn)
            else:
                print('error:zero blk')
        chlen = 0
        next_block = sup.free[0]
        while next_block:
            chlen += 1
            blk = self.read_block(next_block)
            fr = struct.unpack('H', blk[:2])[0]
            if not fr:
                print('abnormal')
                break
            free += fr
            next_block = struct.unpack('H', blk[2:4])[0]
            for i in range(fr):
                blkn = struct.unpack('H', blk[2+i*2:4+i*2])[0]
                if blkn:
                    if blkn in free_blks:
                        print('error: {} block {} repeated'.format(chlen, blkn))
                    free_blks.append(blkn)
                elif next_block or i!=0:
                    print('error: zero blk @', len(free_blks))
        print('chain length:', chlen)
        if len(set(free_blks))!=len(free_blks):
            print('error: free blocks are repeated: {} / {}'.format(len(set(free_blks)), len(free_blks)))
        return free_blks

    def get_used_blocks(self):
        blks = set()
        for node in self.yield_all_inodes():
            for blk in self.yield_node_blocks(node, include_all=True):
                blks.add(blk)
        return list(blks)

    def yield_all_inodes(self):
        sup = self.read_superblock()
        icnt = sup.isize*BLOCK_SIZE//INODE_SIZE
        acnt = 0
        for i in range(1, icnt+1):
            node = self.read_i_node(i)
            if not node.is_allocated():
                continue
            acnt += 1
            yield node
        print('{} allocated / {} possible inodes'.format(acnt, icnt))

    def count_free_blocks(self):
        return len(self.get_free_blocks())

    def integrity(self):
        blks = self.get_used_blocks()
        print('Max block:', max(blks))
        print('Total blocks used:', len(blks))      # TODO: "du /" shows 3 blocks more being used than this
        sup = self.read_superblock()
        all_blocks = len(blks) + self.count_free_blocks() + sup.isize + 2
        print('Total blocks:', all_blocks)
        print('Expected image size:', all_blocks*BLOCK_SIZE)

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
    fs = UnixV6FileSystem(DISK_IMAGE_FILENAME)
    fs.test()

    from sys import argv
    if argv[1] in ['tree', 'extract']:
        if argv[1] == 'tree':
            # Command "tree" prints entire filesystem tree
            size, blk_size = fs.tree(1)
        else:
            # Command "extract" - extracts all the files into new directory
            dst_dir = argv[2]
            src_dir = argv[3] if len(argv)>3 else '/'
            size, blk_size = fs.extract_dir(dst_dir, src_dir)   
        print('Total size: %d, Block size: %d (%d)' % (size, blk_size*BLOCK_SIZE, blk_size))
    
    elif argv[1] == 'mkdir':
        # Command "mkdir" - make new directory
        fs.mkdir(argv[2])

    elif argv[1] == 'exists':
        # Command "exists" - check if file/directory exists
        print(fs.path_exists(argv[2]))

    elif argv[1] == 'upload':
        # Command 'upload' - copy file from local filesystem into Unix V6 filesystem
        fs.upload_file(argv[2], argv[3])

    elif argv[1] == 'sum':
        # Command 'sum' - Unix V5 checksum local file 
        print(fs.sum_file(open(argv[2], 'rb').read()))

    elif argv[1] == 'freeblocks':
        # Command 'freeblocks' - count how many free blocks left according to the Superflock chain
        fbks = fs.count_free_blocks()
        print('Free blocks:', fbks)
        print('Free blocks size:', fbks*BLOCK_SIZE)

    elif argv[1] == 'integrity':
        # Command 'integrity' - simple check for consistency
        fs.integrity()

    elif argv[1] == 'sync':
        # Command 'sync' - synchronize directory with Unix V6
        print (fs.sync(argv[2], argv[3]),'files and directories synced')

    else:
        raise ValueError('unknown command: '+argv[1])
