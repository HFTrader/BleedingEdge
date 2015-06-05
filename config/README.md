# Config

This folder contains two types of files:

1. configuration files

2. custom python builders

The configuration files contain a list of versions. The content of each version is described in more details in the root/README.md. These configs have to follow the convention

    <package>.json

Custom builder files have the name

    <package>.py

    or

    <package>-<version>.py

The variation with the version will has priority if there is an exact match. Otherwise the generic version will be used.
These builders replace - typically they inherit from the standard Builder class and override one of the build methods.
