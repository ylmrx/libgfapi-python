#  Copyright (c) 2012-2015 Red Hat, Inc.
#  This file is part of libgfapi-python project
#  (http://review.gluster.org/#/q/project:libgfapi-python)
#  which is a subproject of GlusterFS ( www.gluster.org)
#
#  This file is licensed to you under your choice of the GNU Lesser
#  General Public License, version 3 or any later version (LGPLv3 or
#  later), or the GNU General Public License, version 2 (GPLv2), in all
#  cases as published by the Free Software Foundation.


import ctypes
import os
import stat
import errno
from gluster import api
from gluster.exceptions import LibgfapiException


class File(object):

    def __init__(self, fd, path=None):
        self.fd = fd
        self.originalpath = path

    def __enter__(self):
        if self.fd is None:
            # __enter__ should only be called within the context
            # of a 'with' statement when opening a file through
            # Volume.open()
            raise ValueError("I/O operation on closed file")
        return self

    def __exit__(self, type, value, tb):
        self.close()

    def close(self):
        ret = api.glfs_close(self.fd)
        if ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return ret

    def discard(self, offset, len):
        ret = api.client.glfs_discard(self.fd, offset, len)
        if ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return ret

    def dup(self):
        dupfd = api.glfs_dup(self.fd)
        if not dupfd:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return File(dupfd, self.originalpath)

    def fallocate(self, mode, offset, len):
        ret = api.client.glfs_fallocate(self.fd, mode, offset, len)
        if ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return ret

    def fchmod(self, mode):
        """
        Change this file's mode

        :param mode: new mode
        :returns: 0 if success, raises OSError if it fails
        """
        ret = api.glfs_fchmod(self.fd, mode)
        if ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return ret

    def fchown(self, uid, gid):
        """
        Change this file's owner and group id

        :param uid: new user id for file
        :param gid: new group id for file
        :returns: 0 if success, raises OSError if it fails
        """
        ret = api.glfs_fchown(self.fd, uid, gid)
        if ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return ret

    def fdatasync(self):
        """
        Force write of file

        :returns: 0 if success, raises OSError if it fails
        """
        ret = api.glfs_fdatasync(self.fd)
        if ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return ret

    def fgetsize(self):
        """
        Return the size of a file, reported by fstat()
        """
        return self.fstat().st_size

    def fstat(self):
        """
        Returns Stat object for this file.
        """
        s = api.Stat()
        rc = api.glfs_fstat(self.fd, ctypes.byref(s))
        if rc < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return s

    def fsync(self):
        ret = api.glfs_fsync(self.fd)
        if ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return ret

    def lseek(self, pos, how):
        """
        Set the read/write offset position of this file.
        The new position is defined by 'pos' relative to 'how'

        :param pos: sets new offset position according to 'how'
        :param how: SEEK_SET, sets offset position 'pos' bytes relative to
                    beginning of file, SEEK_CUR, the position is set relative
                    to the current position and SEEK_END sets the position
                    relative to the end of the file.
        :returns: the new offset position

        """
        return api.glfs_lseek(self.fd, pos, how)

    def read(self, buflen=-1):
        """
        read file

        :param buflen: length of read buffer. If less than 0, then whole
                       file is read. Default is -1.
        :returns: buffer of size buflen
        """
        if buflen < 0:
            buflen = self.fgetsize()
        rbuf = ctypes.create_string_buffer(buflen)
        ret = api.glfs_read(self.fd, rbuf, buflen, 0)
        if ret > 0:
            return rbuf
        elif ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        else:
            return ret

    def write(self, data, flags=0):
        # creating a ctypes.c_ubyte buffer to handle converting bytearray
        # to the required C data type

        if type(data) is bytearray:
            buf = (ctypes.c_ubyte * len(data)).from_buffer(data)
        else:
            buf = data
        ret = api.glfs_write(self.fd, buf, len(buf), flags)
        if ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return ret


class Dir(object):

    def __init__(self, fd):
        # Add a reference so the module-level variable "api" doesn't
        # get yanked out from under us (see comment above File def'n).
        self._api = api
        self.fd = fd
        self.cursor = ctypes.POINTER(api.Dirent)()

    def __del__(self):
        self._api.glfs_closedir(self.fd)
        self._api = None

    def next(self):
        entry = api.Dirent()
        entry.d_reclen = 256
        rc = api.glfs_readdir_r(self.fd, ctypes.byref(entry),
                                ctypes.byref(self.cursor))

        if (rc < 0) or (not self.cursor) or (not self.cursor.contents):
            return rc

        return entry


class Volume(object):

    def __init__(self, host, volname,
                 proto="tcp", port=24007, log_file=None, log_level=7):
        """
        Create a Volume object instance.

        :param host: Host with glusterd management daemon running.
        :param volname: Name of GlusterFS volume to be mounted and used.
        :param proto: Transport protocol to be used to connect to management
                      daemon. Permitted values are "tcp" and "rdma".
        :param port: Port number where gluster management daemon is listening.
        :param log_file: Path to log file. When this is set to None, a new
                         logfile will be created in default log directory
                         i.e /var/log/glusterfs
        :param log_level: Integer specifying the degree of verbosity.
                          Higher the value, more verbose the logging.

        TODO: Provide an interface where user can specify volfile directly
        instead of providing host and other details. This is helpful in cases
        where user wants to load some non default xlator on client side. For
        example, aux-gfid-mount or mount volume as read-only.
        """
        # Add a reference so the module-level variable "api" doesn't
        # get yanked out from under us (see comment above File def'n).
        self._api = api

        self._mounted = False
        self.fs = None
        self.log_file = log_file
        self.log_level = log_level

        if None in (volname, host):
            # TODO: Validate host based on regex for IP/FQDN.
            raise LibgfapiException("Host and Volume name should not be None.")
        if proto not in ('tcp', 'rdma'):
            raise LibgfapiException("Invalid protocol specified.")
        if not isinstance(port, (int, long)):
            raise LibgfapiException("Invalid port specified.")

        self.host = host
        self.volname = volname
        self.protocol = proto
        self.port = port

    @property
    def mounted(self):
        return self._mounted

    def mount(self):
        """
        Mount a GlusterFS volume for use.
        """
        if self.fs and self._mounted:
            # Already mounted
            return

        self.fs = api.glfs_new(self.volname)
        if not self.fs:
            raise LibgfapiException("glfs_new(%s) failed." % (self.volname))

        ret = api.glfs_set_volfile_server(self.fs, self.protocol,
                                          self.host, self.port)
        if ret < 0:
            # FIXME: For some reason, get_errno() is not able to capture
            # proper errno. Until then..
            # https://bugzilla.redhat.com/show_bug.cgi?id=1196161
            raise LibgfapiException("glfs_set_volfile_server(%s, %s, %s, "
                                    "%s) failed." % (self.fs, self.protocol,
                                                     self.host, self.port))

        self.set_logging(self.log_file, self.log_level)

        if self.fs and not self._mounted:
            ret = api.glfs_init(self.fs)
            if ret < 0:
                raise LibgfapiException("glfs_init(%s) failed." % (self.fs))
            else:
                self._mounted = True

    def unmount(self):
        """
        Unmount a mounted GlusterFS volume.

        Provides users a way to free resources instead of just waiting for
        python garbage collector to call __del__() at some point later.
        """
        if self.fs:
            ret = self._api.glfs_fini(self.fs)
            if ret < 0:
                raise LibgfapiException("glfs_fini(%s) failed." % (self.fs))
            else:
                # Succeeded. Protect against multiple unmount() calls.
                self._mounted = False
                self.fs = None

    def __del__(self):
        try:
            self.unmount()
        except LibgfapiException:
            pass

    def set_logging(self, log_file, log_level):
        """
        Set logging parameters. Can be invoked either before or after
        invoking mount().

        When invoked before mount(), the preferred log file and log level
        choices are recorded and then later enforced internally as part of
        mount()

        When invoked at any point after mount(), the change in log file
        and log level is instantaneous.

        :param log_file: Path of log file.
                         If set to "/dev/null", nothing will be logged.
                         If set to None, a new logfile will be created in
                         default log directory (/var/log/glusterfs)
        :param log_level: Integer specifying the degree of verbosity.
                          Higher the value, more verbose the logging.
        """
        if self.fs:
            ret = api.glfs_set_logging(self.fs, self.log_file, self.log_level)
            if ret < 0:
                raise LibgfapiException("glfs_set_logging(%s, %s) failed." %
                                        (self.log_file, self.log_level))
        self.log_file = log_file
        self.log_level = log_level

    def chmod(self, path, mode):
        """
        Change mode of path

        :param path: the item to be modified
        :mode: new mode
        :returns: 0 if success, raises OSError if it fails
        """
        ret = api.glfs_chmod(self.fs, path, mode)
        if ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return ret

    def chown(self, path, uid, gid):
        """
        Change owner and group id of path

        :param path: the item to be modified
        :param uid: new user id for item
        :param gid: new group id for item
        :returns: 0 if success, raises OSError if it fails
        """
        ret = api.glfs_chown(self.fs, path, uid, gid)
        if ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return ret

    def exists(self, path):
        """
        Test whether a path exists.
        Returns False for broken symbolic links.
        """
        try:
            self.stat(path)
        except OSError:
            return False
        return True

    def getatime(self, path):
        """
        Returns the last access time as reported by stat
        """
        return self.stat(path).st_atime

    def getctime(self, path):
        """
        Returns the time when changes were made to the path as reported by stat
        This time is updated when changes are made to the file or dir's inode
        or the contents of the file
        """
        return self.stat(path).st_ctime

    def getmtime(self, path):
        """
        Returns the time when changes were made to the content of the path
        as reported by stat
        """
        return self.stat(path).st_mtime

    def getsize(self, filename):
        """
        Return the size of a file, reported by stat()
        """
        return self.stat(filename).st_size

    def getxattr(self, path, key, maxlen):
        buf = ctypes.create_string_buffer(maxlen)
        rc = api.glfs_getxattr(self.fs, path, key, buf, maxlen)
        if rc < 0:
            err = ctypes.get_errno()
            raise IOError(err, os.strerror(err))
        return buf.value[:rc]

    def isdir(self, path):
        """
        Test whether a path is an existing directory
        """
        try:
            s = self.stat(path)
        except OSError:
            return False
        return stat.S_ISDIR(s.st_mode)

    def isfile(self, path):
        """
        Test whether a path is a regular file
        """
        try:
            s = self.stat(path)
        except OSError:
            return False
        return stat.S_ISREG(s.st_mode)

    def islink(self, path):
        """
        Test whether a path is a symbolic link
        """
        try:
            s = self.lstat(path)
        except OSError:
            return False
        return stat.S_ISLNK(s.st_mode)

    def listdir(self, path):
        """
        Return list of entries in a given directory 'path'.
        "." and ".." are not included, and the list is not sorted.
        """
        dir_list = []
        d = self.opendir(path)
        while True:
            ent = d.next()
            if not isinstance(ent, api.Dirent):
                break
            name = ent.d_name[:ent.d_reclen]
            if name not in [".", ".."]:
                dir_list.append(name)
        return dir_list

    def listxattr(self, path):
        buf = ctypes.create_string_buffer(512)
        rc = api.glfs_listxattr(self.fs, path, buf, 512)
        if rc < 0:
            err = ctypes.get_errno()
            raise IOError(err, os.strerror(err))
        xattrs = []
        # Parsing character by character is ugly, but it seems like the
        # easiest way to deal with the "strings separated by NUL in one
        # buffer" format.
        i = 0
        while i < rc:
            new_xa = buf.raw[i]
            i += 1
            while i < rc:
                next_char = buf.raw[i]
                i += 1
                if next_char == '\0':
                    xattrs.append(new_xa)
                    break
                new_xa += next_char
        xattrs.sort()
        return xattrs

    def lstat(self, path):
        s = api.Stat()
        rc = api.glfs_lstat(self.fs, path, ctypes.byref(s))
        if rc < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return s

    def makedirs(self, name, mode=0777):
        """
        Create directories defined in 'name' recursively.
        """
        head, tail = os.path.split(name)
        if not tail:
            head, tail = os.path.split(head)
        if head and tail and not self.exists(head):
            try:
                self.makedirs(head, mode)
            except OSError as err:
                if err.errno != errno.EEXIST:
                    raise
            if tail == os.curdir:
                return
        self.mkdir(name, mode)

    def mkdir(self, path, mode=0777):
        ret = api.glfs_mkdir(self.fs, path, mode)
        if ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return ret

    def open(self, path, flags, mode=0777):
        if (os.O_CREAT & flags) == os.O_CREAT:
            # FIXME:
            # Without direct call to _api the functest fails on creat and open.

            fd = api.client.glfs_creat(self.fs, path, flags, mode)
        else:
            fd = api.client.glfs_open(self.fs, path, flags)
        if not fd:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))

        return File(fd, path)

    def opendir(self, path):
        fd = api.glfs_opendir(self.fs, path)
        if not fd:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return Dir(fd)

    def removexattr(self, path, key):
        ret = api.glfs_removexattr(self.fs, path, key)
        if ret < 0:
            err = ctypes.get_errno()
            raise IOError(err, os.strerror(err))
        return ret

    def rename(self, opath, npath):
        ret = api.glfs_rename(self.fs, opath, npath)
        if ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return ret

    def rmdir(self, path):
        ret = api.glfs_rmdir(self.fs, path)
        if ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return ret

    def rmtree(self, path, ignore_errors=False, onerror=None):
        """
        Delete a whole directory tree structure. Raises OSError
        if path is a symbolic link.

        :param path: Directory tree to remove
        :param ignore_errors: If True, errors are ignored
        :param onerror: If set, it is called to handle the error with arguments
                        (func, path, exc) where func is the function that
                        raised the error, path is the argument that caused it
                        to fail; and exc is the exception that was raised.
                        If ignore_errors is False and onerror is None, an
                        exception is raised
        """
        if ignore_errors:
            def onerror(*args):
                pass
        elif onerror is None:
            def onerror(*args):
                raise
        if self.islink(path):
            raise OSError("Cannot call rmtree on a symbolic link")
        names = []
        try:
            names = self.listdir(path)
        except OSError as e:
            onerror(self.listdir, path, e)
        for name in names:
            fullname = os.path.join(path, name)
            if self.isdir(fullname):
                self.rmtree(fullname, ignore_errors, onerror)
            else:
                try:
                    self.unlink(fullname)
                except OSError as e:
                    onerror(self.unlink, fullname, e)
        try:
            self.rmdir(path)
        except OSError as e:
            onerror(self.rmdir, path, e)

    def setfsuid(self, uid):
        ret = api.glfs_setfsuid(uid)
        if ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return ret

    def setfsgid(self, gid):
        ret = api.glfs_setfsgid(gid)
        if ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return ret

    def setxattr(self, path, key, value, vlen):
        ret = api.glfs_setxattr(self.fs, path, key, value, vlen, 0)
        if ret < 0:
            err = ctypes.get_errno()
            raise IOError(err, os.strerror(err))
        return ret

    def stat(self, path):
        s = api.Stat()
        rc = api.glfs_stat(self.fs, path, ctypes.byref(s))
        if rc < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return s

    def statvfs(self, path):
        """
        To get status information about the file system that contains the file
        named by the path argument.
        """
        s = api.Statvfs()
        rc = api.glfs_statvfs(self.fs, path, ctypes.byref(s))
        if rc < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return s

    def symlink(self, source, link_name):
        """
        Create a symbolic link 'link_name' which points to 'source'
        """
        ret = api.glfs_symlink(self.fs, source, link_name)
        if ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return ret

    def unlink(self, path):
        """
        Delete the file 'path'

        :param path: file to be deleted
        :returns: 0 if success, raises OSError if it fails
        """
        ret = api.glfs_unlink(self.fs, path)
        if ret < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return ret

    def walk(self, top, topdown=True, onerror=None, followlinks=False):
        """
        Directory tree generator. Yields a 3-tuple dirpath, dirnames, filenames

        dirpath is the path to the directory, dirnames is a list of the names
        of the subdirectories in dirpath. filenames is a list of the names of
        the non-directiry files in dirpath
        """
        try:
            names = self.listdir(top)
        except OSError as err:
            if onerror is not None:
                onerror(err)
            return

        dirs, nondirs = [], []
        for name in names:
            if self.isdir(os.path.join(top, name)):
                dirs.append(name)
            else:
                nondirs.append(name)

        if topdown:
            yield top, dirs, nondirs
        for name in dirs:
            new_path = os.path.join(top, name)
            if followlinks or not self.islink(new_path):
                for x in self.walk(new_path, topdown, onerror, followlinks):
                    yield x
        if not topdown:
            yield top, dirs, nondirs
