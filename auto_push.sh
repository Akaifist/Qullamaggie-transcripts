#!/bin/bash

cd "/Users/akuma/Q's PRD"

git pull --rebase

git add .
git commit -m "Auto sync: $(date)"
git push
