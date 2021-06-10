#!/usr/bin/env python3
import sys
import yaml
import json

if len(sys.argv)<2:
    print( "Usage: json2yaml <filename> [<outfile>]" )
    sys.exit(0)
filename = sys.argv[1]
if len(sys.argv)>2:
    outfile = open(sys.argv[2],'w')
else:
    outfile = sys.stdout
with open(filename,'r') as f:
    data = f.read()
js = json.loads( data )
yml = yaml.dump( js )
print( yml, file=outfile )
