#!/bin/bash

USER=klog
KLOG=/home/${USER}/klog/klog

TMP=$(mktemp)

chmod a+r $TMP
cat > $TMP

sudo -u $USER $KLOG --from-email $TMP
ret=$?

rm $TMP

exit $ret
