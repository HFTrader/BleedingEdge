#!/usr/bin/python
import os
import sys
import subprocess
import urllib2
import shutil
import json
import gzip
import shutil
import copy
import imp
import re,fnmatch
from datetime import datetime
import argparse
import platform as plat
import multiprocessing
import tempfile
import StringIO

def nowstr():
    # Helper to provide timestamp for logging. It's in local time
    return datetime.now().strftime( "%Y/%m/%d %H:%M:%S" )

class BuildManager():
    # This is the build manager. It is the main entry point in the library
    # You need to instantiate one of these and optionally limit the configs
    # by providing a tag like 'bleeding', 'stable', 'fred', etc
    # Make sure these tags exist in the configs otherwise you will end up
    # empty handed as it will not match anything
    def __init__( self,
                  location = "default",
                  tags = ['default',],
                  platform=plat.system(),
                  config="~/.bleedingedge.json" ):
        # This is the default platform
        self.platform = platform
        self.versions = {}
        # as default-ready, get the path of this script
        thisscript = os.path.realpath(__file__)
        self.thisdir = os.path.dirname( thisscript )
        self.numjobs = multiprocessing.cpu_count()

        # you can specify several locations in your ~/.bleedingedge.json file
        # the default would be just 'default'
        # used to filter out all configurations that are not tagged with this
        self.tags = self.readTags( tags )

        # try to open the main config to read where the files will be
        usercfg = os.path.expanduser( config )
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
            self.tmpdir     = setjs.get('tmpdir') or "%s/%s" % (self.repodir,'tmp')
        else:
            # this is a new system - set the defaults to the directory that
            # contains this script
            self.repodir = self.thisdir
            self.builddir =  "%s/build" % (self.repodir,)
            self.installdir = "%s/install" % (self.repodir,)
            self.deploydir  = "%s/deploy" % (self.repodir,)
            self.tmpdir     = "%s/tmp" % ( self.repodir,)

            # write the default config for user's reference so he/she can
            # tweak it later on
            with open( usercfg, "w" ) as f:
                cfg = { 'default':
                        {   'repodir': self.repodir,
                            'builddir': self.builddir,
                            'installdir': self.installdir,
                            'deploydir': self.deploydir,
                            'tmpdir': self.tmpdir } }
                # write a pretty json for their amusement
                f.write( json.dumps( cfg, indent=4, separators=(',',': ') ) )

        # build default directories
        for dname in (self.repodir,self.builddir,self.installdir, self.deploydir):
            try:
                if not os.path.exists( dname ):
                    os.makedirs( dname )
                    print "Created directory", dname
            except Exception, e:
                print "Exception while creating", dname, ": ", e
            if not os.path.exists( dname ):
                print >> sys.stderr, "Error: could not create ", dname
            else:
                if not os.path.isdir( dname ):
                    print >> sys.stderr, "Error: path exists but is not", \
                        "a directory:", dname

    def dumpEnvironment( self ):
        cmd = """
        export PATH=$PATH:{deploydir}/bin
        export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:{deploydir}/lib
        """
        return self.resolve( cmd )

    def parse( self, pkgstring ):
        # this gets complicated because some damn packages have a dash on them as apache-maven
        # we need a routine to parse the command-line and generate a package name and version
        pkgnames = self.getAllPackages()
        splits = pkgstring.split( '-' )
        for j in range(1,len(splits)+1):
            pkgname = '-'.join(splits[0:j])
            version = '-'.join(splits[j:])
            if pkgname in pkgnames:
                return (pkgname,version)
        return None,None

    def updateStatus( self, pkgname, version, done ):
        # we keep the status in the install directory as a touched file
        # with the timestamp of when the deployment has completed
        fname = self.resolve( "{installdir}/{pkgname}-{version}.done",
                              {'pkgname':pkgname,'version':version} )
        if done:
            with open( fname, "w" ) as f:
                f.write( nowstr() )
        else:
            # remove the sentinel
            if os.path.isfile( fname ):
                os.unlink( fname )

    def checkIsBuilt( self, pkgname, version ):
        fname = self.resolve( "{installdir}/{pkgname}-{version}.done",
                              {'pkgname':pkgname,'version':version} )
        return os.path.isfile( fname )

    def build( self, pkgname, version=None ):
        print "Requested build package [%s] version [%s]" % (pkgname,version)

        # Executes all steps to retrieve this package, compile and install in
        # its final destination.
        # First, attempt to check if there are any dependencies. If so, attempt
        # to build them first. Note that the order of the dependencies
        # IS important
        pkg = self.getPackage( pkgname, version )
        if version is None:
            version = pkg.get('version')
            print "Package",pkgname,"version not provided, found:", version
        else:
            print "Package",pkgname,"version:", version, " found:", pkg.get('version')
        self.versions[pkgname+'-version'] = pkg.get('version')

        alldependencies = self.getDependencies( pkgname, version )
        for deps in alldependencies:
            if isinstance(deps,list) or isinstance(deps,tuple):
                depname,depver = deps
            else:
                depname = deps
                depver  = None
            if not self.build( depname, depver ):
                print "Dependency was not satisfied. Bailing out..."
                return False

        # Now that the dependencies are installed, finally proceed with this
        # package's installation procedures.
        # TODO Perhaps we should add a completion test for the configure(), make()
        # and install() steps in the same way we do with checkout()
        print "Searching for builder for package [%s] version [%s]" %(pkgname,version)
        bld = self.getBuilder( pkgname, version )
        bld.numjobs = self.numjobs

        # Check if this package is already deployed
        # we use the builder's version because ours can be None
        if self.checkIsBuilt( pkgname, bld.version ):
            print "Package",pkgname,bld.version,': nothing to do'
            return True

        # sync all dependencies to deploydir
        deploydir = self.resolve( "{deploydir}" )
        print ">> Removing ",deploydir
        if os.path.exists( deploydir ):
            shutil.rmtree( deploydir )
        os.makedirs( deploydir )
        for depname,depver in alldependencies:
            print ">> Deploying ", depname, depver
            dep = self.getBuilder( depname, depver )
            dep.deploy()

        # substitute PATH and LD_LIBRARY_PATH to use our libraries by default
        oldPATH = os.environ.get("PATH","")
        oldLIBPATH = os.environ.get("LD_LIBRARY_PATH","")
        os.environ['PATH'] = ":".join( [oldPATH,self.resolve( "{deploydir}/bin:{deploydir}/x86_64-unknown-linux-gnu/bin" ) ] )
        os.environ['LD_LIBRARY_PATH'] = self.resolve( "{deploydir}/lib:{deploydir}/lib64:{deploydir}/x86_64-unknown-linux-gnu/lib" )

        # Not deployed, go through the compilation process again
        try:
            ok = bld.checkout() and \
                 bld.configure() and \
                 bld.make() and \
                 bld.install()
        except Exception, e:
            ok = False
            print "Exception caught building ", pkgname, version
            print e

        # restore our PATH and LD_LIBRARY_PATH
        os.environ['PATH'] = oldPATH
        os.environ['LD_LIBRARY_PATH'] = oldLIBPATH

        # update this package's status
        self.updateStatus( pkgname, bld.version, ok )
        return ok

    def getAllPackages( self ):
        cfgdir = os.path.join( self.thisdir, 'config' )
        return [ v[:-5] for v in os.listdir( cfgdir )
                    if os.path.isfile( os.path.join(cfgdir,v) )
                    and v.endswith('.json') ]

    def getDependencies( self, pkgname, version=None ):
        # Simply return the 'depends' field in the config file
        # and check for None. We want to return an empty list not None
        # so the for loop does not break
        pkg = self.getPackage( pkgname, version )
        pending = pkg.get('depends')
        if pending is None:
            return []
        deps = {}
        while len(pending)>0:
            depname = pending.pop()
            namver = depname.split('-')
            #print "depname:",depname, " namver:", namver
            dep = self.getPackage( *namver )
            #print "dep:", dep
            if (dep['name'] not in deps) and (not dep['name']==pkgname):
                deps.update( {dep['name']: dep['version']} )
                pending.append( "%s-%s" % (dep['name'],dep['version']) )
        return deps.items()

    def getBuilder( self, pkgname, version=None ):
        # Retrieve the builder object responsible for this particular
        # package and version. We try first to match a python file like
        # <this-script-dir>/gcc-5.1.0.py for gcc version 5.1.0
        # then we try to match
        # <this-script-dir>/gcc.py for gcc (generic)
        # if both are not found, returns just the default Builder
        altfiles = []
        if version:
            altfiles.append( ("%s-%s" % (pkgname,version), "%s/config/%s-%s.py" % (self.thisdir,pkgname,version)) )
        altfiles.append( (pkgname, "%s/config/%s.py" % (self.thisdir,pkgname)) )
        for modname,srcfile in altfiles:
            if os.path.isfile( srcfile ):
                module = imp.load_source( modname, srcfile )
                bld = module.CustomBuilder( self, pkgname, version )
                return bld
        return Builder( self, pkgname, version )

    def getPackage( self, pkgname, version=None ):
        # we make this in two steps because we have to transform
        # the configuration that is in the file and stuff it with defaults
        # if they are not present.
        # Doing this way we also can reuse a config from a previous version and
        # modify them
        pkg = self.__getPackage( pkgname, version )
        if pkg is not None:
            pkg = copy.deepcopy( pkg )
            # Version can be different - we might have specified gcc 4.2.8 but
            # the only config available is gcc 5.1.2 which we assume is o.k.
            if (version is not None) and (not 'version' in pkg):
                pkg['version'] = version
            # 'name' is not a required field since it's implicit on the file
            # location so we just add it here for consistency.
            pkg['name'] = pkgname
        return pkg

    def __getPackage( self, pkgname, version=None ):
        # Then, we need to find a configuration file for this package
        # that resides on the same directory than this script, in
        # config/<packagename>.{platform}.json
        if self.platform=="Linux":
            pkgfile = '%s/config/%s.json' % (self.thisdir,pkgname)
        else:
            pkgfile = '%s/config/%s.%s.json' % (self.thisdir,pkgname,self.platform)
        if not os.path.exists( pkgfile ):
            print "**** ERROR: Package file",pkgfile,"is missing"
            print "            Should be on",pkgfile
            return None
        try:
            with open( pkgfile, "rb" ) as f:
                js = json.loads( f.read() )
        except Exception, e:
            print "Exception while reading from file",pkgfile,":", e
            return None

        # The file can be a list of configurations or just one
        # if configuration is just a dict, meaning there is only one, return it
        if isinstance( js, dict ):
            # Returns it only if this config's tag matches what we've specified
            if self.matchTags( pkgname, js['version'] ):
                print "Could not find a valid configuration with tags:"
                print '    ', ','.join(self.tags)
                return None
            return js

        # pick the version that best approximates AND has our tag (if any)
        # if version is in the form '1.2.3' then we should be able to
        # organize by version number
        allvs = []
        for item in js:
            # pass if this config does not have our tag
            if not self.matchTags( pkgname, item['version'] ):
                continue
            # check if we have a perfect match
            vs = item['version']
            if (version is not None) and (vs==version):
                return item
            # no, canonicalize the version so to pick the best
            key =  [ '%-5s' % v for v in vs.replace('_','.').split('.') ]
            allvs.append( (key,item) )

        # try to find one version whose key is equal or greater the spec
        vskey = [ '%-5s' % v for v in version.replace('_','.').split('.') ] if version else None
        for key,item in sorted( allvs, key=lambda x: x[0], reverse=True ):
            if (not version) or (key<vskey):
                # As the configs are sorted in reverse order, the first
                # one that satisfies this is the lower bound we want
                return item

        # otherwise, return the first version available if everything was wrong
        return js[0]

    # Reads ubuntu version files (trusty, bionic, etc)
    def readUbuntuTag( self, tag ):
            #try:
            url = "https://packages.ubuntu.com/%s/allpackages?format=txt.gz" % (tag,)
            print "Url:", url
            datagz = urllib2.urlopen( url, timeout=15 )
            lre = re.compile( "^(\S+)\s+\((\S+)\)\s+\[(\S+)\]" )
            tagmap = None
            tmpio = StringIO.StringIO()
            tmpio.write( datagz.read() )
            tmpio.seek(0)
            gz = gzip.GzipFile( fileobj=tmpio )

            tagmap = {}
            for line in gz:
                line = line.strip()
                g = lre.match( line )
                if g:
                    name,version,universe = g.groups()
                    #print "Tag", tag, "  pkg:", name, "  ver:", version
                    tagmap[name] = version.split('-')[0]
            gz.close()
            tmpio.close()

            return tagmap

    def readTags( self, tags ):
        # produces a dict of tag => { pkgname => match } for this package
        ver = {}
        for tag in tags:
            fname = os.path.join( self.thisdir, "tags/%s.json" % tag )
            if os.path.isfile( fname ):
                try:
                    with open(fname,'r') as f:
                        tagmap = json.loads( f.read() )
                except Exception, e:
                    print "Tag file",fname," Exception",e
                    return None
            else:
                tagmap = self.readUbuntuTag( tag )
                if not tagmap:
                    print "Tag",tag,"does not exist!"
                    continue
            pkgmap = {}
            for pkgname,verlist in tagmap.iteritems():
                if isinstance(verlist,basestring):
                    verlist = (verlist,)
                matchstr = '|'.join('(?:{0})'.format(fnmatch.translate(x))
                                    for x in verlist)
                pkgmap[pkgname] = re.compile(matchstr)
            ver[tag] = pkgmap
        return ver

    def matchTags( self, pkgname, version ):
        for tag,pkgmap in self.tags.iteritems():
            rexpr = pkgmap.get(pkgname)
            if (rexpr is None) or (rexpr.match(version) is None):
                return False
        return True

    def resolve( self, newval, pkg=None ):
        # Substitutes all {} until there is no more changes
        # The dictionary used on the substitution is a merge between this
        # manager's __dict__ (its fields) and the builder's package from config
        mdict = {}
        mdict.update( self.__dict__ )
        #print "Versions:", self.versions
        mdict.update( self.versions )
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
        self.numjobs  = multiprocessing.cpu_count()
        self.pkg      = buildmgr.getPackage( pkgname, version )
        if self.version != self.pkg['version']:
            print "Replacing",pkgname,"version",version,"with",self.pkg['version']
        self.version  = self.pkg['version']
        self.logfile = self.resolve( "{builddir}/{dirname}.log" )
        self.errfile = self.resolve( "{builddir}/{dirname}.err" )

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

    def download( self, url, pkgfile ):
        if os.path.exists( pkgfile ):
            return True

        print "Downloading [%s] from [%s]" % (pkgfile,url)
        count = 0
        data = None
        while True:
            try:
                usock = urllib2.urlopen(url,timeout=15)
                data = usock.read()
                usock.close()
                break
            except Exception, e:
                print >> sys.stderr, "Exception while downloading",url
                print >> sys.stderr, e
                count += 1
                if count == 5:
                    print "Giving up..."
                    break
        if not data:
            return False
        with open( pkgfile, 'w' ) as fout:
            fout.write( data )
        print "[%s] downloaded to [%s]" % (url, pkgfile)
        return True

    def checkout( self ):
        # Downloads and extracts the tarball file form the web
        # Perhaps we could augment this to include svn/git like from github?
        url = self.resolve( self.pkg['url'] )
        if not url:
            with open( self.errfile, 'a+' ) as errf:
                errf.write( "Configuration missign [url]" )
            return False
        pkgfile = self.pkg.get('pkgfile')
        if not pkgfile:
            if not 'ext' in self.pkg:
                self.pkg['ext'] = self.filetype( url )
            pkgfile = self.resolve( "{builddir}/{name}-{version}.{ext}" )
            self.pkg['pkgfile'] = pkgfile
        fullpath = self.resolve( '{builddir}/{dirname}' )
        if os.path.exists( fullpath ):
            print "Removing existing path", fullpath
            shutil.rmtree( fullpath )
        if url.startswith( 'svn:' ):
            cmd = "cd {builddir} && svn co {url} {dirname}"
            status = self.runcmd( cmd )
            return status==0
        elif url.endswith( '.git' ) or url.startswith( 'git:' ):
            cmd = "cd {builddir} && git clone {url} {dirname}"
            status = self.runcmd( cmd )
            return status==0
        else:
            if not self.download( url, pkgfile ):
                return False
            dirname = self.pkg.get('dirname')
            if not dirname:
                dirname = '{name}-{version}'
                self.pkg['dirname'] = dirname
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
            with open( self.errfile, 'a+' ) as errf:
                errf.write( "Could not identify a valid extension in [%s] for extraction" % (pkgfile,) )
            return False
        if ext=='tar.gz':
            cmd = 'cd {builddir} && tar xzf {pkgfile}'
        elif ext=='tar.xz':
            cmd = 'cd {builddir} && tar xJf {pkgfile}'
        elif ext=='tar.bz2':
            cmd = 'cd {builddir} && tar xjf {pkgfile}'
        elif ext=='zip':
            cmd = 'mkdir -p {builddir}/{name}-{version} && cd {builddir}/{name}.{version}/ && unzip {pkgfile}'
        status = self.runcmd( cmd )
        if status!=0:
            print "Command failed with status", status
        return status == 0

    def runcmd( self, cmd ):
        # Run a system command, funneling stdout and stderr to the respective
        # configuration logs
        cmd = self.resolve( cmd )
        print "Exec:", cmd
        pc = subprocess.Popen( cmd,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               shell=True )
        try:
            out,err = pc.communicate()
        except Exception, e:
            print "Exception running", cmd, ":", e
        if pc.returncode != 0:
            print '\n'.join( err.split('\n')[-30:] )
        logstr = "%s %s\n%s\n" % ("*"*30, nowstr(), cmd)
        with open( self.logfile, 'a+' ) as logf:
            logf.write( logstr )
            logf.write( out )
            logf.flush()
        with open( self.errfile, 'a+' ) as errf:
            errf.write( logstr )
            errf.write( err )
            errf.flush()
        return pc.returncode

    def configure( self ):
        # Try to get the configure command from package configuration
        # This is usually the commnand that changes most frequently
        # This step can also be used to apply patches, if any
        cmd = self.pkg.get('configure') or \
          "./configure --prefix={installdir}/{dirname}"
        cmd = "cd {builddir}/{dirname} && " + cmd
        status = self.runcmd( cmd )
        if status!=0:
            print "Command failed with status %d" % (status)
            return False
        return True

    def make( self ):
        # Try to get the make command from package configuration
        # Otherwise go with just 'make'
        cmd = self.pkg.get('make') or \
          "make -j %d " % (self.numjobs,)
        cmd = "cd {builddir}/{dirname} && " + cmd
        status = self.runcmd( cmd )
        if status!=0:
            print "Command failed with status %d" % (status)
            return False
        return True

    def install( self ):
        # Try to get the install command from package configuration
        # If not found, just run 'make install' which is the usual for 99%
        # of the packages out there
        cmd = self.pkg.get('install') or \
          "make install"
        cmd = "cd {builddir}/{dirname} && " + cmd
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
        cmd = "cd {builddir}/{dirname} && " + cmd
        status = self.runcmd( cmd )
        if status!=0:
            print "Command failed with status %d" % (status)
            print "Check log files",self.logfile,"and",self.errfile
            return False
        return True

if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument( 'packages', nargs='*' )
    parser.add_argument( '--tags', '-t', default='default' )
    parser.add_argument( '--location', '-l', default='default')
    parser.add_argument( '--platform', '-p', default=plat.system())
    parser.add_argument( '--config', '-c', default='~/.bleedingedge.json')
    parser.add_argument( '--jobs', '-j', default=multiprocessing.cpu_count() )
    parser.add_argument( '--dump-environ', '-e', dest='dumpenv',
                         action='store_true', default=False )
    opt = parser.parse_args()

    if len(opt.packages)==0 and (not opt.dumpenv):
        parser.print_help()
        sys.exit(1)

    mytags = opt.tags.split(',') if isinstance(opt.tags,str) else opt.tags
    mgr = BuildManager( tags=mytags, location=opt.location, config=opt.config )
    mgr.numjobs = int( opt.jobs )

    if opt.dumpenv:
        print mgr.dumpEnvironment()
        sys.exit(0)

    if len(opt.packages)==1 and (opt.packages[0].lower()=='all'):
        opt.packages = mgr.getAllPackages()

    for pkg in opt.packages:
        # things get dicy for cases like apache-maven-3.3.3
        # (pkgname,version) = (apache,maven-3.3.3) or (apache-maven,3.3.3)?
        pkgname,version = mgr.parse( pkg )
        if pkgname is None:
            print "Package string",pkg,"does not match any in database"
            continue
        if not mgr.build( pkgname, version ):
            break
