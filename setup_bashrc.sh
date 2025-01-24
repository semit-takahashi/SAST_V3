#!/bin/bash
echo ".bashrc add SAST scripts..."

cat >> ~/.bashrc <<- "EOF"
## ADD SAST SCRIPTS
SAST_DIR='SAST_V301'
alias ll='ls -l'
alias la='ls -A'
alias l='ls -CF'
alias shut='sudo shutdown -h now'
alias log='tail -f /var/log/sast.log'
alias dlog="tail -f $HOME/$SAST_DIR/SAST-debug.log"
alias elog="tail -f $HOME/$SAST_DIR/stderr.log"
alias pps='ps -aef | grep python'
alias killP='sudo killall python3'
alias battery='echo "get battery" | nc -q 0 127.0.0.1 8423'
alias start="cd ${HOME}/${SAST_DIR}; /bin/bash start.sh"
echo ''
cat /proc/device-tree/model
echo ''
EOF
