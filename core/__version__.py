# Copyright 2024 The habitat Authors. All rights reserved.
# Licensed under the Apache License Version 2.0 that can be found in the
# LICENSE file in the root directory of this source tree.

VERSION = (0, 3, 127)

alpha = None
rc = None
suffix = None

__version__ = '.'.join(map(str, VERSION))

if alpha is not None:
    __version__ += f"-alpha.{alpha}"
elif rc is not None:
    __version__ += f"-rc.{rc}"

if suffix:
    __version__ += f"-{suffix}"
