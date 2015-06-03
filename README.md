# BleedingEdge

## Motivation

BleedingEdge is a simple package manager to help build development versions of important libraries.

The need for a script like this came when I needed to maintain one C++ package that needed to be tested with several versions of GCC and CLANG.

The key design aspects are:

1. Keep and install repositories as a user, no root/superuser required
2. Be simple to create and maintain
3. Support multiple versions of the same package

## How it works

The package works with one script as the entry point, the one at root:

`    pkgbuild.py`

I'm still working on the command line so <right now> you'd have to hack into the `__main__` in the script and customize it to be usable. What's there as an example is the compilation of gcc 4.9.2.

The script when starts, should instantiate one BuildManager object, whose constructor takes two parameters:

1. location - this allows you to have several configurations defined in your ~/.bleedingedge.json file (hidden) for several purposes. Eg I use one location for each package I have to test.
2. tag - this filters out packages and allows you to have otherwise duplicate configurations for say 'mingw', 'ubuntu', 'bleeding', 'stable', 'redhat-old', etc. It's really a mechanism to allow flexibility and contribution.

Then, the script would typically call mgr.deploy( pkgname ) or mgr.deploy( pkgname, version ).

The builder will search for a valid configuration in the following location:

`    <scriptdir>/config/<pkgname>/package.json`

Within this configuration file (in json format duh) there should be a list of configs. These configs will be scanned for a match, which will be:

1. one that matches the tags specified, if any

2. has the exact version as specified

3. the one that has the highest version that is lower than the version the user specified - this is a lower bound

Here is a description of the fields that are supported in the configuration.

- version: most used of fields. It indicates the particular version that this package is in. It should be in the format of a dot-separated string as '1.2.3' but we dont particularly enforce that. One needs to be careful that version strings are transformed in keys to be used when we need to find a version that is not an exact match. This is described below.

- url: Where to download the tarball from. You would usually use the key {dirname}. it is okay to put the version number explicitly here but beware that if say, user asks for binutils version 2.27 and the last available is 2.25, the 2.25 config will be used. In this case, if the URL is specified as `ftp.gnu.org/gnu/binutils/binutils-2.25.tar.gz` then we will not be able to pick up the 2.27 version from the ftp site. You will have to create another entry in the config, which is not ideal. So please use the {dirname} key.

- dirname: the name of this key is not intuitive but I could not find a better one. It is the name of the directory under config (and under build) that will hold configs and the build, respectively. Examples are `binutils-2.25` and `gcc-5.0.1`. The configuration directory, for example, will be `<yourscriptdir>/config/gcc-5.0.1/`. I've added the default to all the configs so far just to make it explicit.

- configure: the script that will prepare the code to build. It defaults to `./configure --prefix={installdir}/{dirname}` but I've added the default to the configs so far for clarity as well. This is the place where you would include all your patches as well.

- make: the shell script that will compile the code. The default is `make`.

- install: the shell script that will install/stage the file. It defaults to `make install`.

- deploy: the shell script that will deploy the file to its final location. This defaults to an rsync and you should not modify it.

- depends: list with all dependencies. Each dependency can be a single string, without mention to the version as "zlib" or a tuple/list with the name and version as in ("zlib","2.5"). In the case that you omit the version, you should then trust that the tag you provided will filter out the versions you dont want.

Notice that you could add your own fields and refer to them in your action scripts, that's completely valid.

The algorithm that I came up to normalize version numbers is very simple - I split the version and pad each part with zeros. Eg if the version is 1.2.3 then the normalized version will be 00001.00002.00003. I'm sure there's something smarter than this - please test and contribute! But it's working fine so far.

Once a configuration is found, the manager will try to find a specialized builder for that package and version. Right now there are none. But I thought of leaving this opening here in the case that we come across some crazy package that needs special treatment. The custom builder would be in

`    <scriptdir>/config/<pkgname>/<pkgname>-<version>.py `

or

`    <scriptdir>/config/<pkgname>/<pkgname>.py `

This python script should contain one class called 'Builder', which will be instantiated. It needs to contain the same methods that in the Builder original. You are welcome to create the first custom!

In BuildManager.deploy() the manager will attempt to call these methods of the builder in sequence:

1. checkout() - this step is supposed to generate the code that needs to be built. The default builder will download a tarball from the specified location in its configuration (`url`) and then untar/unzip this file into the respective location in the repository build - which is specified in your ~/.bleedingedge.json.

2. configure() - this step will make modifications in the code and prepare it to be compiled. The default builder will simply execute the contents of the key 'configure' in the configuration. If not present, it defaults to`./configure --prefix <installdir>/{dirname}`, which is sufficient for most packages.

3. make() - this step is the actual compilation of the files in the project. The default builder will execute the 'make' tag in the configuration or, if not present, call 'make' in the build directory.

4. install() - this step takes care of installing the binaries into a secluded location within the repository tree. The default builder will execute the code within the key 'install' in its configuration or 'make install' if this key is not found.

5. deploy() - this step copies the files from its install directory into the final deployment location. The default builder will execute the code in the key 'deploy' or simply 'rsync -av {installdir}/{dirname} {deploydir}' if 'deploy' is not found in the configuration.

There are many advantages on having this staging 2-step process of install and deploy. It is cleaner and allows one to create packages (think rpm or debian) which is not implemented yet but it's in the plans.

Hope you enjoy this work.

Please contribute.

This project is possible thanks to [Vitorian LLC](http://www.vitorian.com) and [HB Quant] (http://www.hbquant.com).
