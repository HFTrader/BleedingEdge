#!/usr/bin/python

# clang has an awkward tree configuration so we have to implement
# a custom builder to override the default downloader

import pkgbuild

class CustomBuilder( pkgbuild.Builder ):
    def __init__( self, buildmgr, pkgname, version ):
        pkgbuild.Builder.__init__( self, buildmgr, pkgname, version )

    def checkout( self ):
        fullpath = self.resolve( '{builddir}/{dirname}' )
        baseurl = self.resolve( self.pkg["url"] )
        for subpkg in ( 'llvm','cfe','compiler-rt','clang-tools-extra'):
            filename = '%s-%s.src.tar.xz' % (subpkg,self.version,)
            pkgfile = self.resolve( '{builddir}/%s' % (filename,) )
            url = '%s/%s' % (baseurl,filename,)
            if not self.download( url, pkgfile ):
                print "Could not download", url
                return False

        cmd = """
        cd {builddir}
        rm -rf {builddir}/clang-{version}

        # untar all packages
        tar xJvf {builddir}/llvm-{version}.src.tar.xz
        tar xJvf {builddir}/cfe-{version}.src.tar.xz
        tar xJvf {builddir}/clang-tools-extra-{version}.src.tar.xz
        tar xJvf {builddir}/compiler-rt-{version}.src.tar.xz
        mv llvm-{version}.src clang-{version}

        # move to respective places
        mv cfe-{version}.src clang-{version}/tools/clang
        mv clang-tools-extra-{version}.src clang-{version}/tools/clang/tools/extra
        mv compiler-rt-{version}.src clang-{version}/projects/compiler-rt

        """
        status = self.runcmd( cmd )
        if status!=0:
            print "Command failed. Please check logs"
        return status==0
