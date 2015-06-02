# BleedingEdge
BleedingEdge is a simple package manager to help build development versions of important libraries.
The need for a script like this came when I needed to maintain one C++ package that needed to be tested with several versions of GCC and CLANG.
The key design aspects are:
1. Keep and install repositories as a user, no root/superuser required
2. Be simple to create and maintain
3. Support multiple versions of the same package
