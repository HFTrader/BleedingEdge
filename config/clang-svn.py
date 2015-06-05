#!/usr/bin/python

# clang has an awkward tree configuration so we have to implement
# a custom builder to override the default downloader

import pkgbuild

class CustomBuilder( pkgbuild.Builder ):
    def __init__( self, buildmgr, pkgname, version ):
        pkgbuild.Builder.__init__( self, buildmgr, pkgname, version )

    def checkout( self ):
        cmd = """
        rm -rf {builddir}/clang-{version} || exit 1
        cd {builddir} || exit 1
        svn co http://llvm.org/svn/llvm-project/llvm/trunk clang-{version} || exit 1

        cd {builddir}/clang-{version}/tools || exit 1
        svn co http://llvm.org/svn/llvm-project/cfe/trunk clang || exit 1

        cd {builddir}/clang-{version}/tools/clang/tools || exit 1
        svn co http://llvm.org/svn/llvm-project/clang-tools-extra/trunk extra || exit 1

        cd {builddir}/clang-{version}/projects || exit 1
        svn co http://llvm.org/svn/llvm-project/compiler-rt/trunk compiler-rt || exit 1
        """
        status = self.runcmd( cmd )
        if status!=0:
            print "Command failed. Please check logs"
        return status==0
