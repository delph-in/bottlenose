#!/usr/bin/env python3

import sys, os

# maybe hardcode this for server deployment
cwd = os.path.dirname(__file__)

# Add the path on the server to the bottlenose installation
sys.path.insert(1, cwd)

# Change working directory so relative paths (and template lookup) work again
os.chdir(cwd)

# ... build or import your bottle application here ...
import bottlenose
# bottlenose.cors_origin = '*'
# bottlenose.cwd = cwd

# Do NOT use bottle.run() with mod_wsgi
application = bottlenose.app

