import dulwich.index as dindex
import errno
import hashlib
import os
import subprocess
from collections import OrderedDict
from _bisect import bisect_left


class GitHasher:
    """
    Single-use object that calculates a hash for a series of files and
    directories (aka trees) using a GitHashRepo.

    Can be constructed with a dir path or a GitHashRepo, in which case
    repo.update() must have already been called.
    """
    def __init__(self, dir=None, repo=None):
        if dir:
            self.repo = GitHashRepo(dir)
            self.repo.update()
        elif repo:
            self.repo = repo
        else:
            raise ValueError("Requires either dir or repo")
        self.hash = hashlib.sha1()

    def add_file(self, file):
        filehash = self.repo.file(file)
        self.hash.update(filehash)

    def add_tree(self, prefix):
        treehash = self.repo.tree(prefix)
        self.hash.update(treehash)

    def digest(self):
        return self.hash.hexdigest()


class NoSuchFileError(ValueError):
    def __init__(self, file):
        ValueError.__init__(self, "No such file: %s" % file)
        self.file = file


class TypeMismatchError(ValueError):
    def __init__(self, file):
        ValueError.__init__(self, "Type mismatch: %s" % file)
        self.file = file


class GitHashRepo:
    """
    GitHashRepo leverages git to calculate checksums for files and directories.
    It uses `git add -A` to checksum files with index and object storage in
    /.githash.

    It can be run in a dir that is also a normal git repo, but it is recommended
    to add /.githash to the gitignore.  Both to avoid checking in those files,
    and to keep git add -A from indexing its own metadata on repeated runs.

    Benefits of using git to create file checksums:

    * The index works as a fast cache of file checksums.  It has logic
      to re-hash files only when their mod time changes.
    * File modes, empty directories, symlinks etc are checksummed as they would
      be by git.  Ie, two users sharing code through git will produce the same
      checksums for the files (modulo dirs containing files that are not ignored
      and are not pushed).
    * It automatically ignores the same files as git.
    """
    def __init__(self, repo_dir):
        self.repo_dir = repo_dir
        self.repo_dir_slash = os.path.join(self.repo_dir, '')
        self.dotdir = os.path.join(repo_dir, '.githash')
        self.index_file = os.path.join(self.dotdir, 'index')
        self.objects = os.path.join(self.dotdir, 'objects')

    def mkdir(self, dir):
        try:
            os.mkdir(dir)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

    def update(self):
        """
        Update must be called before file() or tree().  It can be called
        again when files are known to have changed.
        :return:
        """
        self.mkdir(self.dotdir)

        process = subprocess.Popen(['git', 'add', '-A'],
                                   env={'GIT_INDEX_FILE': self.index_file},
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   cwd=self.repo_dir)
        stdout, stderr = process.communicate()
        retcode = process.poll()
        if retcode:
            raise RuntimeError(stderr.strip())

        self._create_index()

        return stdout.strip()

    def file(self, file):
        norm_file = self._norm_path(file)
        try:
            entry = self.index[norm_file]
            return self._entry_str(entry, norm_file)
        except KeyError:
            raise NoSuchFileError(file)

    def tree(self, prefix):
        norm_prefix = self._norm_path(prefix)

        paths = [p for p in self._subpaths(norm_prefix)]
        if len(paths) == 0:
            raise NoSuchFileError(prefix)

        res = [self._entry_str(self.index[p], p) for p in paths]
        return b"\n".join(res)

    def _create_index(self):
        self.index = OrderedDict()
        with open(self.index_file) as f:
            for x in dindex.read_index(f):
                self.index[x[0]] = dindex.IndexEntry(*x[1:])

    def _subpaths(self, path):
        keys = self.index.keys()
        i = bisect_left(keys, path)
        while i < len(keys):
            key = keys[i]
            if key.startswith(path):
                yield key
                i += 1
            else:
                break

    def _norm_path(self, path):
        if path.startswith(self.repo_dir_slash):
            return path[len(self.repo_dir_slash):]
        else:
            return path

    @staticmethod
    def _entry_str(entry, path):
        # To be encoding-agnostic, ensure that values are bytes, and return
        # a byte string.
        assert(isinstance(entry.sha, (str, bytes, bytearray)))
        assert(isinstance(path, (str, bytes, bytearray)))

        mode = b'%o' % dindex.cleanup_mode(entry.mode)
        return b"{mode} {sha} 0\t{file}".format(mode=mode,
                                                sha=entry.sha,
                                                file=path)
    