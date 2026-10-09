#!/bin/bash
# the number of cores depends on the machine
sed -i "s/^CPU_CORES = 0 .*/CPU_CORES = $(nproc)/" answers.py
