# Tags

This folder will hold files with the following name convention:

    <tagname>.json

Each json file will contain a dictionary (map) of

    <packagename> : <version>

    or

    <packagename> : [ <version1>, <version2>, ... ]

Each `<version>` can be a string or a wildcard as defined by `python.fsmatch`, ie a filesystem-like wildcard.

Examples:

    {
    "gcc" : [ "4.8.5", "4.9.*", "5.*" ],
    "clang" : "3.5.0"
    }
