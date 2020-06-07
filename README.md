githash: fast file checksums by leaning on git

- TODO: avoid writing any .githash/objects (eg `git update-index --info-only`)
- TODO: test on python3
- TODO: port to pygit2?
- TODO: setup.py

I'm sharing this to demonstrate the idea.  The unit tests pass and the library has been battle
tested, but it needs some improvements.  If you find it and wish you could `pip install` it, let me
know (@etuttle).  Or, I'll fix it up next time I have a use case for it.

## Original use case: content addressable build artifacts

If a build system tags its output wth a checksum of the inputs, the output become "content
addressable".  That's great, because the system can avoid building the same thing twice: before
building, checksum the inputs and see if the output already exists.

Such a system has to repeatedly checksum every input.  That would be unbearably slow, but there's an
optimization: note the mod time of each file as it is checksummed. Then cache the filename, mod
time, and the checksum for later use.  Subsequent runs only need to stat each file and checksum the
ones that changed, according to the mod time.

## Implementation

The idea of `githash` is that `git` implements that optimized checksum cache, and it can be used for
purposes other than SCM.

See the comments in the `GitHashRepo` class for more details and justifications.

## Unit tests

Nose2 works, just be sure to remove the .py from the test filename:

```sh
pip install nose2
nose2 githash_test
```
