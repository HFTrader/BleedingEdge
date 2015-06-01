#!/usr/bin/python
import os
import sys
import subprocess
import urllib
import json
import shutil

class Builder:
    def __init__( self, repodir, builddir=None, installdir=None, deploydir=None ):
        self.repodir = repodir
        self.builddir = builddir or "%s/%s" % (self.repodir,'build')
        self.installdir = installdir or "%s/%s" % (self.repodir,'install')
        self.deploydir  = deploydir or "%s/%s" % (self.repodir,'deploy')
        self.builders = {}
        for dname in (self.repodir,self.builddir,self.installdir, self.deploydir):
            try:
                os.makedirs( dname )
                print "Created directory", dname
            except Exception, e:
                pass
            if not os.path.exists( dname ):
                print >> sys.stderr, "Error: could not create ", dname
            else:
                if not os.path.isdir( dname ):
                    print >> sys.stderr, "Error: path exists but is not", \
                        "a directory:", dname
        pkgfile = '%s/packages.json' % self.repodir
        if not os.path.exists( pkgfile ):
            print "**** ERROR: Package file",pkgfile,"is missing"
        try:
            with open( pkgfile, "rb" ) as f:
                js = json.loads( f.read() )
                for item in js:
                    self.builders[ item['name'] ] = item
        except Exception, e:
            print "**** ERROR parsing", pkgfile, ": \n", e

    def install( self, pkgname ):
        pkg = self.builders.get( pkgname )
        if not pkg:
            print "Cannot find builder for ", pkgname
            return
        self.checkout( pkg )
        self.configure( pkg )
        self.make( pkg )
        self.install( pkg )

    def register( self, regs ):
        self.builders[ regs['name'] ] = regs

    def resolve( self, newval, pkg=None ):
        mdict = self.__dict__
        if pkg:
            mdict.update( pkg )
        value = None
        while not (newval == value):
            value = newval
            newval = value.format( **mdict )
            #print "Resolve: oldvalue=%s newvalue=%s" % (value,newval)
        return newval

    def filetype( self, filename ):
        fnlow = filename.lower()
        if fnlow.endswith( '.tar.gz' ) or fnlow.endswith( 'tgz' ):
            return 'tar.gz'
        if fnlow.endswith( '.tar.xz' ):
            return 'tar.xz'
        if fnlow.endswith( '.tar.bz2' ):
            return 'tar.bz2'
        if fnlow.endswith( '.tar' ):
            return 'tar'
        if fnlow.endswith( '.zip' ):
            return 'zip'

    def checkout( self, pkgname ):
        pkg = self.builders.get( pkgname )
        if not pkg:
            print "Cannot find package", pkgname
            return None
        url = self.resolve( pkg['url'], pkg )
        if not url:
            print "Configuration missign [url]"
            return None
        pkgfile = pkg.get('pkgfile')
        if not pkgfile:
            if not 'ext' in pkg:
                pkg['ext'] = self.filetype( url )
                #print "File type is ", pkg['ext']
            pkgfile = self.resolve( "{repodir}/{name}-{version}.{ext}", pkg )
            pkg['pkgfile'] = pkgfile
        if os.path.exists( pkgfile ) and os.path.isfile( pkgfile ):
            return pkgfile
        if not url:
            print "Cannot resolve [url]"
            return None
        try:
            filename,headers = urllib.urlretrieve( url )
            print url
            print "Downloaded to ", filename
        except Exception, e:
            print "Exception while downloading", url, ":", e
            return None
        try:
            shutil.move( filename, pkgfile )
        except Exception, e:
            print "Exception while moving",filename,'to',pkgfile
            return None
        return pkgfile

    def extract( self, pkgname ):
        pkg = self.builders.get( pkgname )
        if not pkg:
            print "Cannot find package", pkgname
            return None
        pkgfile = pkg.get('pkgfile') or self.checkout( pkgname )
        if not pkgfile:
            return None
        dirname = pkg.get('dirname')
        if not dirname:
            dirname = '{name}-{version}'
            pkg['dirname'] = dirname
        fullpath = self.resolve( '{builddir}/{dirname}', pkg )
        print "Fullpath:", fullpath
        if os.path.exists( fullpath ):
            print "Removing existing path", fullpath
            shutil.rmtree( fullpath )
        ext = pkg.get('ext') or self.filetype( pkgfile )
        if not ext:
            return None
        if ext=='tar.gz':
            cmd = 'cd {builddir}; tar xzvf {pkgfile}'
        elif ext=='tar.xz':
            cmd = 'cd {builddir}; tar xJvf {pkgfile}'
        elif ext=='tar.bz2':
            cmd = 'cd {builddir}; tar xjvf {pkgfile}'
        elif ext=='zip':
            cmd = 'mkdir -p {builddir}/{name}-{version}; cd {builddir}/{name}.{version}/; unzip {pkgfile}'
        cmd = self.resolve( cmd, pkg )
        logfile = self.resolve( "{builddir}/{dirname}.log", pkg )
        errfile = self.resolve( "{builddir}/{dirname}.err", pkg )
        with open(logfile,'a+') as logf, open(errfile,'a+') as errf:
            status = subprocess.call( cmd, stdout=logf, stderr=errf, shell=True )
        #print status
        return pkg

    def build( self, pkgname ):
        pkg = self.extract( pkgname )
        outdir = self.resolve( '{builddir}/{dirname}', pkg )
        print outdir

if __name__=="__main__":
    bld = Builder( "/mnt/Scratch/bleedingedge" )
    bld.build( 'zlib' )
