import errno
import hashlib
import os
import subprocess


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
    It uses `git add -A` to checksum files, and `git write-tree` to checksum
    directories, with index and object storage in /.githash.

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
        self.index = os.path.join(self.dotdir, 'index')
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
                                   env={'GIT_INDEX_FILE': self.index},
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   cwd=self.repo_dir)
        stdout, stderr = process.communicate()
        retcode = process.poll()
        if retcode:
            raise RuntimeError(stderr.strip())
        return stdout.strip()

    def file(self, file):
        normfile = self.normpath(file)

        process = subprocess.Popen(['git', 'ls-files', '--stage', normfile],
                                   env={'GIT_INDEX_FILE': self.index},
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   cwd=self.repo_dir)
        stdout, stderr = process.communicate()
        retcode = process.poll()
        if retcode:
            raise RuntimeError(stderr.strip())
        lines = stdout.splitlines()
        if len(lines) == 0:
            raise NoSuchFileError(file)
        if len(lines) > 1:
            raise TypeMismatchError(file)
        if lines[0].split('\t')[1] != normfile:
            raise TypeMismatchError(file)
        return lines[0]

    def tree(self, prefix):
        norm_prefix = self.normpath(prefix)

        # TODO this creates a bunch of files in .githash/objects.  Needs GC?
        self.mkdir(self.objects)
        process = subprocess.Popen(['git', 'write-tree', '--missing-ok',
                                    '--prefix', norm_prefix],
                                   env={'GIT_INDEX_FILE': self.index,
                                        'GIT_OBJECT_DIRECTORY': self.objects},
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   cwd=self.repo_dir)
        stdout, stderr = process.communicate()
        retcode = process.poll()
        if retcode:
            if 'prefix %s not found' % norm_prefix in stderr:
                raise NoSuchFileError(prefix)
            raise Exception(stderr.strip())
        return stdout.strip()

    def normpath(self, path):
        if path.startswith(self.repo_dir_slash):
            return path[len(self.repo_dir_slash):]
        else:
            return path
