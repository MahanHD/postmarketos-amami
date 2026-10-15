#!/bin/sh
# Development phone: when the session ends (logout or crash), restart LightDM
# so autologin runs again instead of leaving the greeter up.
systemd-run --on-active=2 --unit=lightdm-relogin-$$ systemctl restart lightdm
