# Copyright Jay Conrod. All rights reserved.
#
# This file is part of Gypsum. Use of this source code is governed by
# the GPL license that can be found in the LICENSE.txt file.


import utils
import yaml


def getFlagByName(name):
    return _flagNames[name]


def canonicalizeFlagName(name):
    return _canonicalFlags[name]


def checkFlagConflicts(flags):
    for group in _flagGroups:
        conflict = group & flags
        if len(conflict) > 1:
            return conflict
    return None


def flagSetToFlagBits(flagSet):
    return reduce(lambda bits, flag: bits | _flagsToCodes[flag], flagSet, 0)


def flagBitsToFlagSet(flagBits):
    code = 1
    flags = []
    while flagBits != 0:
        if (flagBits & code) != 0:
            flags.append(_codesToFlags[code])
            flagBits ^= code
        code <<= 1
    return frozenset(flags)


_flagsToCodes = {}
_codesToFlags = {}
_canonicalFlags = {}
_flagNames = {}
_flagGroups = []

_initialized = False

def _initialize():
    global _initialized
    if _initialized:
        return
    _initialized = True
    with utils.openCommonFile("flags.yaml") as flagsFile:
        flagList = yaml.load(flagsFile.read())
    code = 1
    for flagName in flagList:
        globals()[flagName] = flagName

        _flagsToCodes[flagName] = code
        _codesToFlags[code] = flagName
        _canonicalFlags[flagName] = flagName
        _flagNames[flagName.lower()] = flagName
        code <<= 1
    _flagGroups.append(frozenset([PUBLIC, PROTECTED, PRIVATE]))
    _flagGroups.append(frozenset([COVARIANT, CONTRAVARIANT]))
    _flagGroups.append(frozenset([ABSTRACT, FINAL]))
    _flagGroups.append(frozenset([ABSTRACT, NATIVE]))
_initialize()

__all__ = ["getFlagByName", "checkFlagConflicts", "flagSetToFlagBits"] + \
        _flagNames.values()
