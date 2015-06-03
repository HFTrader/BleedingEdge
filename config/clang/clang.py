#!/usr/bin/python

# clang has an awkward tree configuration so we have to implement
# a custom builder to override the default downloader

import pkgbuild

class CustomBuilder( pkgbuild.Builder ):
    def __init__( self, buildmgr, pkgname, version ):
        pkgbuild.Builder( buildmgr, pkgname, version )

    def checkout( self ):
        fullpath = self.resolve( '{builddir}/{dirname}' )
        baseurl = self.resolve( self.pkg["url"] )
        for subpkg in ( 'llvm','cfe','compiler-rt','clang-tools-extra'):
            filename = '%s-%s.src.tar.xz' % (subpkg,self.version,)
            url = '%s/%s' % (baseurl,pkgfile,)
            pkgfile = self.resolve( '{builddir}/%s' % (filename,) )
            if not self.download( url, pkgfile ):
                print "Could not download", url
                return False

        cmd = """
        cd {builddir}

        # untar all packages
        tar xJvf {builddir}/llvm-{version}.src.tar.xz
        tar xJvf {builddir}/cfe-{version}.src.tar.xz
        tar xJvf {builddir}/clang-tools-extra-{version}.src.tar.xz
        tar xJvf {builddir}/compiler-rt-{version}.src.tar.xz

        # move to respective places
        mv clang-{version} llvm-{version}/tools/clang
        mv clang-tools-extra-{version} llvm-{version}/tools/clang/tools/extra
        mv compiler-rt-{version} llvm-{version}/projects/compiler-rt

        """
        return self.runcmd( cmd )
