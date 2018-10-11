#!/usr/bin/env python3

import sys, os

# Maybe hardcode this for server deployment
cwd = os.path.dirname(__file__)

# Add the path on the server to the bottlenose installation
sys.path.insert(1, cwd)

# Change working directory so relative paths (and template lookup) work again
os.chdir(cwd)

# Now import the application
import bottlenose
application = bottlenose.app

