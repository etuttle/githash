from githash import *
from unittest.case import TestCase
import os
import shutil
import subprocess
import tempfile


class TestGitHashBase(TestCase):

    def cmd(self, cmd):
        return subprocess.check_output(cmd, shell=True, cwd=self.test_repo)

    def setUp(self):
        self.test_repo = tempfile.mkdtemp()
        with open(os.path.join(self.test_repo, '.gitgnore'), 'w') as f:
            f.write('/.githash')
        self.cmd('git init')
        self.repo = GitHashRepo(self.test_repo)

    def tearDown(self):
        shutil.rmtree(self.test_repo)

    def mkfile(self, name, contents, mode=0644):
        file = os.path.join(self.test_repo, name)
        with open(file, 'w') as f:
            f.write(contents)
        os.chmod(file, mode)

    def mkdir(self, name):
        dir = os.path.join(self.test_repo, name)
        os.mkdir(dir)

    def mklink(self, target, name):
        link = os.path.join(self.test_repo, name)
        os.symlink(target, link)

class TestGitHashRepo(TestGitHashBase):

    def test_update(self):
        self.mkfile('file', 'hello')
        self.repo.update()
        self.assertTrue(os.path.exists(self.repo.index_file))

    def test_file(self):
        self.mkfile('file', 'hello')
        self.repo.update()
        filestr = self.repo.file('file')
        self.assertEqual('100644 b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0 0	file', filestr)

        # full prefix path should work as well
        filestr = self.repo.file(os.path.join(self.test_repo, 'file'))
        self.assertEqual('100644 b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0 0	file', filestr)

    def test_exefile(self):
        self.mkfile('file', 'hello', 0777)
        self.repo.update()
        filestr = self.repo.file('file')
        self.assertEqual('100755 b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0 0	file', filestr)

    def test_nosuchfile(self):
        self.repo.update()
        with self.assertRaises(NoSuchFileError) as ve:
            self.repo.file('file')
        self.assertEqual(ve.exception.message, 'No such file: file')

    def test_dir_as_file(self):
        self.mkdir('dir')
        self.mkfile('dir/file', 'hello')
        self.repo.update()
        with self.assertRaises(NoSuchFileError):
            self.repo.file('dir')

    def test_tree(self):
        self.mkdir('dir')
        self.mkfile('dir/file', 'hello')
        self.mkfile('dir/file2', 'hello2')
        self.repo.update()

        expected = """100644 b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0 0\tdir/file
100644 23294b0610492cf55c1c4835216f20d376a287dd 0\tdir/file2"""

        treestr = self.repo.tree('dir')
        self.assertEqual(expected, treestr)

        # full prefix path should work as well
        treestr = self.repo.tree(os.path.join(self.test_repo, 'dir'))
        self.assertEqual(expected, treestr)

    def test_nosuchtree(self):
        self.repo.update()
        with self.assertRaises(NoSuchFileError) as ve:
            self.repo.tree('dir')
        self.assertEqual(ve.exception.message, 'No such file: dir')

    def test_file_as_tree(self):
        self.mkdir('dir')
        self.mkfile('dir/file', 'hello')
        self.repo.update()
        res = self.repo.tree('dir/file')
        self.assertEqual('100644 b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0 0	dir/file', res)

    def test_link(self):
        self.mklink('hello', 'link')
        self.repo.update()
        linkstr = self.repo.file('link')
        self.assertEqual('120000 b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0 0	link', linkstr)

    def test_link2(self):
        self.mklink('hello2', 'link')
        self.repo.update()
        linkstr = self.repo.file('link')
        self.assertEqual('120000 23294b0610492cf55c1c4835216f20d376a287dd 0	link', linkstr)


class TestGitHasher(TestGitHashBase):
    def file_test(self, mode, expected):
        self.mkfile('file', 'hello', mode)
        self.repo.update()
        hasher = GitHasher(repo=self.repo)
        hasher.add_file('file')
        self.assertEqual(expected, hasher.digest())

    def tree_test(self, mode, expected, append_slash=False):
        self.mkdir('dir')
        self.mkfile('dir/file', 'hello', mode)
        self.repo.update()
        hasher = GitHasher(repo=self.repo)
        hasher.add_tree('dir/' if append_slash else 'dir')
        self.assertEqual(expected, hasher.digest())

    def test_file(self):
        self.file_test(0644, '1240074d3d7c5e73bcf0f2ed42c34990c58dab44')

    def test_exefile(self):
        self.file_test(0777, '95d8f52325cfd9d98471eff781a843bd01e62aa5')

    def test_tree(self):
        self.tree_test(0644, 'edff93fcd48450d0b3f5a2977da1b5a2e7a5d015')

    def test_tree_slash(self):
        self.tree_test(0644, 'edff93fcd48450d0b3f5a2977da1b5a2e7a5d015',
                       append_slash=True)

    def test_exetree(self):
        self.tree_test(0777, '4bd31b14f7a237cacc22ed5d10e4d867c7201300')

    def test_tree_and_file(self):
        self.mkdir('dir')
        self.mkfile('dir/file', 'hello')
        self.mkfile('file2', 'hello2')
        self.repo.update()
        hasher = GitHasher(repo=self.repo)
        hasher.add_tree('dir')
        hasher.add_file('file2')
        self.assertEqual('53b08c1fc6223d0c326e2146a5ccf8dbccf8223b', hasher.digest())

    def test_hash_meta(self):
        hasher = GitHasher(repo=self.repo)
        hasher.add_meta('a', '1')
        self.assertEqual('f29bc91bbdab169fc0c0a326965953d11c7dff83', hasher.digest())

        hasher = GitHasher(repo=self.repo)
        hasher.add_meta('a', '2')
        hasher.add_meta('a', '1')
        self.assertEqual('f29bc91bbdab169fc0c0a326965953d11c7dff83', hasher.digest())

        hasher = GitHasher(repo=self.repo)
        hasher.add_meta('a', '1')
        hasher.add_meta('b', '2')
        self.assertEqual('87f7ff9d1e933e7b40a6b46cc6a3c6663247d915', hasher.digest())

        hasher = GitHasher(repo=self.repo)
        hasher.add_meta('b', '2')
        hasher.add_meta('a', '1')
        self.assertEqual('87f7ff9d1e933e7b40a6b46cc6a3c6663247d915', hasher.digest())
