#!/usr/bin/env python

from __future__ import division # confidence high

import os
import string
import StringIO
import logging

# Configure the logger to write message to a string buffer.
# This will allow the messages to be output at the end of
# the setup process.
logging.basicConfig(level=logging.WARNING)
finalMessages = StringIO.StringIO()
console = logging.StreamHandler(finalMessages)
logging.getLogger('').addHandler(console)

# We use the local copy of stsci_distutils_hack, unless
# the user asks for the stpytools version
try :
    import stsci.tools.stsci_distutils_hack as H
except ImportError :
    import stsci_distutils_hack as H

H.run()

# Output any warnings issued during the processing.
if finalMessages.getvalue() != '':
    print ""

    s = string.split(finalMessages.getvalue(),'\n')

    for i in range(len(s)):

        if i == 0:
            print "WARNING: %s" % (s[i])
        else:
            print "         %s" % (s[i])


