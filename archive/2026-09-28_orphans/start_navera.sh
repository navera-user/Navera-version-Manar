#!/bin/bash
docker run -it --rm \
  --runtime nvidia \
  --privileged \
  --device /dev/nvmap \
  --device /dev/nvhost-ctrl \
  --device /dev/nvhost-gpu \
  --name navera-container \
  -v /home/navera/isaac_ros_common:/workspaces/isaac_ros-dev \
  -v /home/navera/isaac_ros_common/.torch_cache:/root/.cache/torch \
  -p 5000:5000 \
  navera_isaac_ros:stable bash
