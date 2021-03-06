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
        self.meta = {}

    def add_file(self, f):
        file_hash = self.repo.file(f)
        self.hash.update(file_hash)

    def add_tree(self, prefix):
        tree_hash = self.repo.tree(prefix)
        self.hash.update(tree_hash)

    def add_meta(self, key, value):
        self.meta[key] = value

    def digest(self):
        self._hash_meta()
        return self.hash.hexdigest()

    def _hash_meta(self):
        for k in sorted(self.meta.keys()):
            self.hash.update(k)
            self.hash.update(self.meta[k])


class NoSuchFileError(ValueError):
    def __init__(self, file):
        ValueError.__init__(self, "No such file: %s" % file)
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
        self.dot_dir = os.path.join(repo_dir, '.githash')
        self.index_file = os.path.join(self.dot_dir, 'index')
        self.objects = os.path.join(self.dot_dir, 'objects')

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
        self.mkdir(self.dot_dir)

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

        paths = [p for p in self._sub_paths(norm_prefix)]
        if len(paths) == 0:
            raise NoSuchFileError(prefix)

        res = [self._entry_str(self.index[p], p) for p in paths]
        return b"\n".join(res)

    def _create_index(self):
        """
        Read the index into an OrderedDict to preserve the key order.  The key
        order established in the index is used when enumerating sub-paths,
        so it must be stable to get a deterministic hash.
        :return: OrderedDict of path to IndexEntry
        """
        self.index = OrderedDict()
        with open(self.index_file) as f:
            for x in dindex.read_index(f):
                self.index[x[0]] = dindex.IndexEntry(*x[1:])

    def _sub_paths(self, path):
        """
        Generator for sub-paths of path in the index, in index order.  This
        assumes that the index key order matches python's sort order.
        """
        keys = self.index.keys()
        # bisect to find the first index with key "greater than or equal to"
        # path, then scan forward checking that sub-paths start with path
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

        # this returns a format similar to git ls-files
        mode = b'%o' % dindex.cleanup_mode(entry.mode)
        return b"{mode} {sha} 0\t{file}".format(mode=mode,
                                                sha=entry.sha,
                                                file=path)
    