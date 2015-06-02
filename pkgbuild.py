#!/usr/bin/python
import os
import sys
import subprocess
import urllib2
import json
import shutil
import copy
import imp
from datetime import datetime

class BuildManager():
    # This is the build manager. It is the main entry point in the library
    # You need to instantiate one of these and optionally limit the configs
    # by providing a tag like 'bleeding', 'stable', 'fred', etc
    # Make sure these tags exist in the configs otherwise you will end up
    # empty handed as it will not match anything
    def __init__( self, location = "default", tag = None ):
        # you can specify several locations in your ~/.bleedingedge.json file
        # the default would be just 'default'
        # used to filter out all configurations that are not tagged with this
        self.tag = tag

        # as default-ready, get the path of this script
        thisscript = os.path.realpath(__file__)
        self.thisdir = os.path.dirname( thisscript )

        # try to open the main config to read where the files will be
        usercfg = os.path.expanduser( "~/.bleedingedge.json" )
        if os.path.isfile( usercfg ):
            # found main config, read
            with open( usercfg ) as f:
                js = json.loads( f.read() )
            setjs = js.get( location )
            if setjs is None:
                print "*** ERROR Location",location,"is not specified in",usercfg
                return
            # default all to repodir/... whenever not specified
            self.repodir = setjs.get('repodir') or self.thisdir
            self.builddir = setjs.get('builddir') or "%s/%s" % (self.repodir,'build')
            self.installdir = setjs.get('installdir') or "%s/%s" % (self.repodir,'install')
            self.deploydir  = setjs.get('deploydir')  or "%s/%s" % (self.repodir,'deploy')
        else:
            # this is a new system - set the defaults to the directory that
            # contains this script
            self.repodir = self.thisdir
            self.builddir =  "%s/build" % (self.repodir,)
            self.installdir = "%s/install" % (self.repodir,)
            self.deploydir  = "%s/deploy" % (self.repodir,)
            # write the default config for user's reference so he/she can
            # tweak it later on
            with open( usercfg, "w" ) as f:
                cfg = { 'default':
                        {   'repodir': self.repodir,
                            'builddir': self.builddir,
                            'installdir': self.installdir,
                            'deploydir': self.deploydir } }
                # write a pretty json for their amusement
                f.write( json.dumps( cfg, indent=4, separators=(',',': ') ) )

        # Cache package configuration - is this necessary?
        self.cache = {}

        # build default directories
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

    def deploy( self, pkgname, version=None ):
        # Executes all steps to retrieve this package, compile and install in
        # its final destination.
        # First, attempt to check if there are any dependencies. If so, attempt
        # to install/deploy them first. Note that the order of the dependencies
        # IS important
        for deps in self.getDependencies( pkgname, version ):
            if isinstance(deps,list):
                depname,depver = deps
            else:
                depname = deps
                depver  = None
            print ">> Deploying dependency",depname,depver
            if not self.deploy( depname, depver ):
                print "Dependency was not satisfied. Bailing out..."
                return False

        # Now that the dependencies are installed, finally proceed with this
        # package's installation procedures.
        # Perhaps we should add a completion test for the configure(), make(),
        # install() and deploy() steps in the same way we do with checkout()
        bld = self.getBuilder( pkgname, version )
        return  bld.checkout() and \
                bld.configure() and \
                bld.make() and \
                bld.install() and \
                bld.deploy()

    def getDependencies( self, pkgname, version=None ):
        # Simply return the 'depends' field in the config file
        # and check for None. We want to return an empty list not None
        # so the for loop does not break
        pkg = self.getPackage( pkgname, version )
        deps = pkg.get('depends')
        if deps is None:
            return []
        return deps

    def getBuilder( self, pkgname, version=None ):
        # Retrieve the builder object responsible for this particular
        # package and version. We try first to match a python file like
        # <this-script-dir>/config/gcc-5.1.0.py for gcc version 5.1.0
        # then we try to match
        # <this-script-dir>/config/gcc.py for gcc (generic)
        # if both are not found, returns just the default Builder
        altfiles = []
        if version:
            altfiles.append( "%s/config/%s-%s.py" % (self.thisdir,pkgname,version) )
        altfiles.append( "%s/config/%s.py" % (self.thisdir,pkgname) )
        for srcfile in altfiles:
            if os.path.isfile( srcfile ):
                mname = self.resolve( '{name}-{version}' )
                module = imp.load_source( mname, srcfile )
                bld = module.Builder( self, pkgname, version )
                self.cache[ (pkgname, version) ] = bld
                return bld
        return Builder( self, pkgname, version )

    def getPackage( self, pkgname, version=None ):
        # retrieves the configuration for a given package and version
        # First, check if we have done this before and it is in cache
        pkg = self.cache.get( (pkgname,version) )
        if pkg is not None:
            return self.cache[ (pkgname,version) ]

        # Then, we need to find a configuration file for this package
        # that resides on the same directory than this script, in
        # config/<packagename>/package.json
        pkgfile = '%s/config/%s/package.json' % (self.thisdir,pkgname)
        if not os.path.exists( pkgfile ):
            print "**** ERROR: Package file",pkgfile,"is missing"
            print "            Should be on",pkgfile
            return None
        with open( pkgfile, "rb" ) as f:
            js = json.loads( f.read() )

        # The file can be a list of configurations or just one
        # if configuration is just a dict, meaning there is only one, return it
        if isinstance( js, dict ):
            # Returns it only if this config's tag matches what we've specified
            if (self.tag is not None) and ('tags' in js):
                if not self.tag in js['tags']:
                    print "Could not find a valid configuration tagged with", self.tag
                    return False
            # Just update this config with our name and version
            # 'name' is not a required field since it's implicit on the file
            # location so we just add it here for consistency.
            # Version can be different - we might have specified gcc 4.2.8 but
            # the only config available is gcc 5.1.2 which we assume is o.k.
            js['name'] = pkgname
            if version:
                js['version'] = version
            return js

        # pick the version that best approximates AND has our tag (if any)
        # if version is in the form '1.2.3' then we should be able to
        # organize by version number
        allvs = []
        for item in js:
            # pass if this config does not have our tag
            if (self.tag is not None) and ('tags' in item):
                if not self.tag in item['tags']:
                    continue
            # check if we have a perfect match
            vs = item['version']
            if version is not None and vs==version:
                item['name'] = pkgname
                self.cache[ (pkgname,version) ] = item
                return item
            # no, canonicalize the version so to pick the best
            key = '.'.join( [ '%-5s' % v for v in vs.split('.') ])
            allvs.append( (key,item) )

        # try to find one version whose key is equal or greater the spec
        if version:
            vskey = '.'.join( [ '%-5s' % v for v in version.split('.') ])
            for key,item in sorted( allvs, key=lambda x: x[0], reverse=True ):
                if key<vskey:
                    # As the configs are sorted in reverse order, the first
                    # one that satisfies this is the lower bound we want
                    print "Found ",pkgname," version ", item['version']
                    item = copy.deepcopy( item )
                    item['name'] = pkgname
                    item['version'] = version # we know version is not None
                    self.cache[ (pkgname,version) ] = item
                    return item

        # otherwise, return the first version available if everything was wrong
        item = copy.deepcopy(js[0])
        item['name'] = pkgname
        if version:
            item['version'] = version
        self.cache[ (pkgname,version) ] = item
        return item

    def resolve( self, newval, pkg=None ):
        # Substitutes all {} until there is no more changes
        # The dictionary used on the substitution is a merge between this
        # manager's __dict__ (its fields) and the builder's package from config
        mdict = {}
        mdict.update( self.__dict__ )
        if pkg:
            mdict.update( pkg )
        value = None
        while not (newval == value):
            value = newval
            newval = value.format( **mdict )
            #print "Resolve: oldvalue=%s newvalue=%s" % (value,newval)
        return newval

class Builder:

    def __init__(self,buildmgr,pkgname,version):
        # Retrieves a package of configuration from the manager
        # and initializes the log streams
        self.buildmgr = buildmgr
        self.pkgname  = pkgname
        self.version  = version
        self.pkg      = buildmgr.getPackage( pkgname, version )
        self.logfile = self.resolve( "{builddir}/{dirname}.log" )
        self.errfile = self.resolve( "{builddir}/{dirname}.err" )
        self.logf = open( self.logfile,'a+')
        self.errf = open( self.errfile,'a+')

    def filetype( self, filename ):
        # Canonicalize the type of compression/zippping mechanism from a file name
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

    def resolve( self, value ):
        # Resolves all {} dependencies in a string
        return self.buildmgr.resolve( value, self.pkg )

    def checkout( self ):
        # Downloads and extracts the tarball file form the web
        # Perhaps we could augment this to include svn/git like from github?
        url = self.resolve( self.pkg['url'] )
        if not url:
            self.errf.write( "Configuration missign [url]" )
            return False
        pkgfile = self.pkg.get('pkgfile')
        if not pkgfile:
            if not 'ext' in self.pkg:
                self.pkg['ext'] = self.filetype( url )
            pkgfile = self.resolve( "{builddir}/{name}-{version}.{ext}" )
            self.pkg['pkgfile'] = pkgfile
        if not os.path.exists( pkgfile ):
            try:
                print "Downloading [%s] from [%s]" % (pkgfile,url)
                usock = urllib2.urlopen(url)
                data = usock.read()
                usock.close()
                with open( pkgfile, 'w' ) as fout:
                    fout.write( data )
                print "[%s] downloaded to [%s]" % (url, pkgfile)
            except Exception, e:
                print >> sys.stderr, "Exception while downloading [%s]: %s" % (url,e)
                return False
        dirname = self.pkg.get('dirname')
        if not dirname:
            dirname = '{name}-{version}'
            self.pkg['dirname'] = dirname
        fullpath = self.resolve( '{builddir}/{dirname}' )
        return self.extract( pkgfile, fullpath )

    def extract( self, pkgfile, fullpath ):
        # extracts the file (name) passed into the canonical directory
        # Currently it understands gzip, bz2, xz and zip
        # This has not been tested with zip!!!
        if os.path.exists( fullpath ):
            print "Removing existing path", fullpath
            shutil.rmtree( fullpath )
        ext = self.pkg.get('ext') or self.filetype( pkgfile )
        if not ext:
            self.errf.write( "Could not identify a valid extension in [%s] for extraction" % (pkgfile,) )
            return False
        if ext=='tar.gz':
            cmd = 'cd {builddir}; tar xzvf {pkgfile}'
        elif ext=='tar.xz':
            cmd = 'cd {builddir}; tar xJvf {pkgfile}'
        elif ext=='tar.bz2':
            cmd = 'cd {builddir}; tar xjvf {pkgfile}'
        elif ext=='zip':
            cmd = 'mkdir -p {builddir}/{name}-{version}; cd {builddir}/{name}.{version}/; unzip {pkgfile}'
        status = self.runcmd( cmd )
        if status!=0:
            print "Command failed with status", status
        return status == 0

    def now( self ):
        # Helper to provide timestamp for logging. It's in local time
        return datetime.now().strftime( "%Y/%m/%d %H:%M:%S" )

    def runcmd( self, cmd ):
        # Run a system command, funneling stdout and stderr to the respective
        # configuration logs
        cmd = self.resolve( cmd )
        logstr = "%s %s\n%s\n" % ("*"*30, self.now(), cmd)
        self.logf.write( logstr )
        self.logf.flush()
        self.errf.write( logstr )
        self.errf.flush()
        print "Exec:", cmd
        status = subprocess.call( cmd, stdout=self.logf, stderr=self.errf,
                                  shell=True )
        self.logf.flush()
        self.errf.flush()
        return status

    def configure( self ):
        # Try to get the configure command from package configuration
        # This is usually the commnand that changes most frequently
        # This step can also be used to apply patches, if any
        cmd = self.pkg.get('configure') or \
          "./configure --prefix={installdir}/{dirname}"
        cmd = "cd {builddir}/{dirname}; " + cmd
        status = self.runcmd( cmd )
        if status!=0:
            print "Command failed with status %d" % (status)
            print "Check log files",self.logfile,"and",self.errfile
            return False
        return True

    def make( self ):
        # Try to get the make command from package configuration
        # Otherwise go with just 'make'
        cmd = self.pkg.get('make') or \
          "make -j4"
        cmd = "cd {builddir}/{dirname}; " + cmd
        status = self.runcmd( cmd )
        if status!=0:
            print "Command failed with status %d" % (status)
            print "Check log files",self.logfile,"and",self.errfile
            return False
        return True

    def install( self ):
        # Try to get the install command from package configuration
        # If not found, just run 'make install' which is the usual for 99%
        # of the packages out there
        cmd = self.pkg.get('install') or \
          "make install"
        cmd = "cd {builddir}/{dirname}; " + cmd
        status = self.runcmd( cmd )
        if status!=0:
            print "Command failed with status %d" % (status)
            print "Check log files",self.logfile,"and",self.errfile
            return False
        return True

    def deploy( self ):
        # Try to get the deploy commnd from package configuration
        # the default is just to rsync from {installdir}/{dirname}
        # into {deploydir} so everything stays in the same place
        cmd = self.pkg.get('deploy') or \
          "rsync -av {installdir}/{dirname}/ {deploydir}/"
        cmd = "cd {builddir}/{dirname}; " + cmd
        status = self.runcmd( cmd )
        if status!=0:
            print "Command failed with status %d" % (status)
            print "Check log files",self.logfile,"and",self.errfile
            return False
        return True

if __name__=="__main__":
    # this is just an example of usage
    # we need to add some command line options here to the script is usable
    # in standalone mode
    print "This is just an example of how to use BE install gcc"
    mgr = BuildManager( tag="stable" )
    mgr.deploy( 'gcc' )

    # or use the more fine-grained approach
    mgr = BuildManager()
    bld = mgr.getBuilder( "gcc", "4.9.2" )
    bld.checkout() and \
      bld.configure() and \
      build.make() and \
      build.install() and \
      build.deploy()
